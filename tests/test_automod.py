import datetime
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import discord
from discord.ext import commands

from cogs.automod import (
    AutoMod,
    is_word_match,
    is_scam_link,
    is_dangerous_attachment,
)
from utils.database import init_db, update_automod_config


@pytest.fixture
async def temp_db(tmp_path):
    db_file = str(tmp_path / "test_automod.db")
    await init_db(db_file)
    yield db_file


@pytest.fixture
def mock_bot(temp_db):
    bot = MagicMock(spec=commands.Bot)
    bot.user = MagicMock(spec=discord.ClientUser)
    bot.user.id = 11111111
    bot.db_path = temp_db
    return bot


@pytest.fixture
def automod_cog(mock_bot):
    cog = AutoMod(mock_bot)
    cog.db_path = mock_bot.db_path
    return cog


def create_mock_message(author_id=555, content="hello world", guild_id=12345):
    msg = MagicMock(spec=discord.Message)
    msg.id = 99901
    msg.content = content
    msg.created_at = datetime.datetime.now(datetime.timezone.utc)
    msg.mentions = []
    msg.role_mentions = []
    msg.attachments = []
    msg.delete = AsyncMock()

    author = MagicMock(spec=discord.Member)
    author.id = author_id
    author.bot = False
    author.mention = f"<@{author_id}>"
    author.guild_permissions = discord.Permissions(send_messages=True)
    author.roles = []
    author.timeout = AsyncMock()
    author.send = AsyncMock()
    msg.author = author

    guild = MagicMock(spec=discord.Guild)
    guild.id = guild_id
    msg.guild = guild

    channel = MagicMock(spec=discord.TextChannel)
    channel.mention = "#general"
    msg.channel = channel

    return msg


def test_word_filter_no_false_positives():
    banned = ["ass"]
    # "grass" and "classic" should NOT match "ass"
    assert is_word_match("I love green grass", banned) is False
    assert is_word_match("That is a classic song", banned) is False
    assert is_word_match("Pass the ball", banned) is False

    # True positives
    assert is_word_match("You are an ass", banned) is True
    assert is_word_match("Don't be an a$$", banned) is True
    assert is_word_match("what an @ss", banned) is True


def test_scam_link_detection():
    # Legitimate domains should NOT trigger
    assert is_scam_link("Check out https://discord.com/channels/123/456") is False
    assert is_scam_link("Join our server at https://discord.gg/welcome") is False
    assert is_scam_link("https://steamcommunity.com/id/gamer") is False

    # Scam / Phishing domains MUST trigger
    assert is_scam_link("Get free nitro at https://dlscord.gift/nitro") is True
    assert is_scam_link("Claim gift: https://discorcl-gift.xyz/claim") is True
    assert is_scam_link("Free discord nitro here: https://discord-nitro.site") is True
    assert is_scam_link("Free steam gifts: https://steamcommunity-tradeoffer.gift") is True


def test_dangerous_attachment_filter():
    safe_att = MagicMock(spec=discord.Attachment)
    safe_att.filename = "screenshot.png"
    assert is_dangerous_attachment([safe_att]) is None

    danger_att = MagicMock(spec=discord.Attachment)
    danger_att.filename = "free_nitro.exe"
    assert is_dangerous_attachment([danger_att]) == "free_nitro.exe"

    bat_att = MagicMock(spec=discord.Attachment)
    bat_att.filename = "installer.bat"
    assert is_dangerous_attachment([bat_att]) == "installer.bat"


@pytest.mark.asyncio
async def test_scam_link_action_deletes_and_timeouts(automod_cog, temp_db):
    msg = create_mock_message(content="Free Nitro here: https://dlscord.gift/free")
    with patch("cogs.automod.send_log", new_callable=AsyncMock) as mock_send_log:
        await automod_cog.on_message(msg)
        msg.delete.assert_called_once()
        msg.author.timeout.assert_called_once()
        mock_send_log.assert_called_once()


@pytest.mark.asyncio
async def test_duplicate_spam_triggers_timeout(automod_cog, temp_db):
    msg1 = create_mock_message(content="Testing duplicate message spam.")
    msg2 = create_mock_message(content="Testing duplicate message spam.")
    msg3 = create_mock_message(content="Testing duplicate message spam.")

    with patch("cogs.automod.send_log", new_callable=AsyncMock) as mock_send_log:
        await automod_cog.on_message(msg1)
        assert not msg1.delete.called

        await automod_cog.on_message(msg2)
        assert not msg2.delete.called

        # 3rd identical message in 10s -> trigger
        await automod_cog.on_message(msg3)
        msg3.delete.assert_called_once()
        msg3.author.timeout.assert_called_once()
        mock_send_log.assert_called_once()
