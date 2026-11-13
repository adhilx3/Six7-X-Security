import pytest
from unittest.mock import AsyncMock, MagicMock
import discord
from discord import app_commands
from discord.ext import commands

from cogs.config_cog import ConfigCog
from utils.database import (
    init_db,
    get_antinuke_config,
    get_automod_config,
    is_antinuke_whitelisted,
)


@pytest.fixture
async def temp_db(tmp_path):
    db_file = str(tmp_path / "test_config.db")
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
def config_cog(mock_bot):
    cog = ConfigCog(mock_bot)
    cog.db_path = mock_bot.db_path
    return cog


def create_mock_interaction(guild_id=12345):
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild_id = guild_id
    interaction.guild = MagicMock(spec=discord.Guild)
    interaction.guild.id = guild_id
    interaction.guild.name = "Config Test Guild"
    interaction.user = MagicMock(spec=discord.Member)
    interaction.user.id = 99999
    interaction.user.mention = "<@99999>"
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()
    return interaction


@pytest.mark.asyncio
async def test_antinuke_commands(config_cog, temp_db):
    inter = create_mock_interaction()

    # Toggle
    await config_cog.antinuke_toggle.callback(config_cog, inter, False)
    cfg = await get_antinuke_config(inter.guild_id, db_path=temp_db)
    assert cfg["enabled"] == 0

    # Whitelist Add
    target = MagicMock(spec=discord.User)
    target.id = 77777
    target.mention = "<@77777>"
    await config_cog.antinuke_whitelist_add.callback(config_cog, inter, target, "Backup Admin")
    assert await is_antinuke_whitelisted(inter.guild_id, target.id, db_path=temp_db) is True

    # Whitelist Remove
    await config_cog.antinuke_whitelist_remove.callback(config_cog, inter, target)
    assert await is_antinuke_whitelisted(inter.guild_id, target.id, db_path=temp_db) is False


@pytest.mark.asyncio
async def test_automod_word_commands(config_cog, temp_db):
    inter = create_mock_interaction()

    # Add word
    await config_cog.add_banned_word.callback(config_cog, inter, "phishing")
    cfg = await get_automod_config(inter.guild_id, db_path=temp_db)
    assert "phishing" in cfg["banned_words"]

    # Remove word
    await config_cog.remove_banned_word.callback(config_cog, inter, "phishing")
    cfg2 = await get_automod_config(inter.guild_id, db_path=temp_db)
    assert "phishing" not in cfg2["banned_words"]


@pytest.mark.asyncio
async def test_security_status_embed(config_cog, temp_db):
    inter = create_mock_interaction()
    await config_cog.security_status.callback(config_cog, inter)
    inter.response.send_message.assert_called_once()
    kwargs = inter.response.send_message.call_args[1]
    embed = kwargs.get("embed")
    assert embed is not None
    assert "Security Status" in embed.title
    field_names = [f.name for f in embed.fields]
    assert "🛡️ Anti-Nuke" in field_names
    assert "🚨 Anti-Raid" in field_names
    assert "🤖 Auto-Mod" in field_names
