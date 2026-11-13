import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import discord
from discord.ext import commands

from cogs.moderation import Moderation, can_moderate
from utils.database import init_db, get_warnings, add_warning


@pytest.fixture
async def temp_db(tmp_path):
    db_file = str(tmp_path / "test_moderation.db")
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
def moderation_cog(mock_bot):
    cog = Moderation(mock_bot)
    cog.db_path = mock_bot.db_path
    return cog


def create_mock_member(user_id=222, top_role_pos=50, owner_id=999):
    member = MagicMock(spec=discord.Member)
    member.id = user_id
    member.mention = f"<@{user_id}>"
    member.guild = MagicMock(spec=discord.Guild)
    member.guild.id = 12345
    member.guild.owner_id = owner_id
    member.top_role = MagicMock(spec=discord.Role)
    member.top_role.position = top_role_pos
    member.kick = AsyncMock()
    member.ban = AsyncMock()
    member.timeout = AsyncMock()
    member.send = AsyncMock()
    return member


def test_can_moderate_hierarchy():
    owner_id = 999
    bot_member = create_mock_member(user_id=111, top_role_pos=100, owner_id=owner_id)
    mod_member = create_mock_member(user_id=222, top_role_pos=80, owner_id=owner_id)
    target_lower = create_mock_member(user_id=333, top_role_pos=30, owner_id=owner_id)
    target_equal = create_mock_member(user_id=444, top_role_pos=80, owner_id=owner_id)
    target_higher = create_mock_member(user_id=555, top_role_pos=90, owner_id=owner_id)
    owner_member = create_mock_member(user_id=owner_id, top_role_pos=150, owner_id=owner_id)

    # Mod can moderate lower target
    allowed, _ = can_moderate(mod_member, target_lower, bot_member)
    assert allowed is True

    # Mod cannot moderate self
    allowed, msg = can_moderate(mod_member, mod_member, bot_member)
    assert allowed is False
    assert "yourself" in msg

    # Mod cannot moderate owner
    allowed, msg = can_moderate(mod_member, owner_member, bot_member)
    assert allowed is False
    assert "server owner" in msg

    # Mod cannot moderate equal or higher target
    allowed, msg = can_moderate(mod_member, target_equal, bot_member)
    assert allowed is False
    assert "higher than yours" in msg

    allowed, msg = can_moderate(mod_member, target_higher, bot_member)
    assert allowed is False
    assert "higher than yours" in msg

    # Bot cannot moderate if bot role is lower than target
    bot_weak = create_mock_member(user_id=111, top_role_pos=20, owner_id=owner_id)
    allowed, msg = can_moderate(mod_member, target_lower, bot_weak)
    assert allowed is False
    assert "higher than mine" in msg


@pytest.mark.asyncio
async def test_warn_persists_in_db(moderation_cog, temp_db):
    guild_id = 12345
    mod = create_mock_member(user_id=100, top_role_pos=80)
    target = create_mock_member(user_id=200, top_role_pos=20)
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild_id = guild_id
    interaction.guild = mod.guild
    interaction.guild.me = create_mock_member(user_id=111, top_role_pos=100)
    interaction.user = mod
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()

    with patch("cogs.moderation.send_log", new_callable=AsyncMock) as mock_send_log:
        await moderation_cog.warn.callback(moderation_cog, interaction, target, "Spamming in chat")
        interaction.response.send_message.assert_called_once()
        mock_send_log.assert_called_once()

        warns = await get_warnings(guild_id, target.id, db_path=temp_db)
        assert len(warns) == 1
        assert warns[0]["reason"] == "Spamming in chat"
        assert warns[0]["moderator_id"] == mod.id

