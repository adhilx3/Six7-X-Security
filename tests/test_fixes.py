import os
import json
import pytest
from unittest.mock import AsyncMock, MagicMock
import discord
from discord.ext import commands

from bot import SecurityBot
from cogs.automod import is_scam_link
from cogs.antinuke import AntiNuke
from cogs.antiraid import AntiRaid
from utils.database import (
    init_db,
    get_guild_config,
    update_guild_config,
    get_antiraid_config,
    get_lockdown_states,
    migrate_from_json,
)


@pytest.fixture
async def temp_db(tmp_path):
    db_file = str(tmp_path / "test_fixes.db")
    await init_db(db_file)
    yield db_file


@pytest.mark.asyncio
async def test_bot_extension_loading_no_collisions():
    """Verifies that all 7 extensions load into SecurityBot without command collisions."""
    import sys
    saved_cogs = {k: v for k, v in sys.modules.items() if k.startswith("cogs.")}
    bot = SecurityBot()
    try:
        for ext in (
            "cogs.antinuke",
            "cogs.moderation",
            "cogs.automod",
            "cogs.antiraid",
            "cogs.verification",
            "cogs.logging_cog",
            "cogs.config_cog",
        ):
            await bot.load_extension(ext)

        # Command tree sync should succeed without duplicates
        commands_list = bot.tree.get_commands()
        command_names = [cmd.name for cmd in commands_list]
        assert len(command_names) == len(set(command_names)), f"Duplicate slash commands found: {command_names}"
    finally:
        for ext in list(bot.extensions.keys()):
            await bot.unload_extension(ext)
        sys.modules.update(saved_cogs)


def test_discord_cdn_attachments_not_scam():
    assert is_scam_link("https://cdn.discordapp.com/attachments/123/456/photo.png") is False
    assert is_scam_link("https://media.discordapp.net/attachments/123/456/photo.png") is False
    assert is_scam_link("https://discordapp.com/channels/123/456") is False


def test_typosquatted_steam_phishing():
    assert is_scam_link("Claim gift: https://steamcommunlty.com/trade/offer") is True
    assert is_scam_link("Free items: https://steamcornmunity.com/gift") is True
    assert is_scam_link("Trade here: https://stearncommunity.com/id/trade") is True


def test_bracketed_and_markdown_scam_links():
    assert is_scam_link("Check this: <https://discorcl.gift/nitro>") is True
    assert is_scam_link("Claim here: [Free Nitro](https://dlscord.app/free)") is True


@pytest.mark.asyncio
async def test_audit_user_resolution_does_not_fallthrough():
    cog = AntiNuke(MagicMock())
    guild = MagicMock(spec=discord.Guild)

    # Mock entry with a different target ID
    entry = MagicMock()
    entry.target = MagicMock()
    entry.target.id = 888  # Different from searched target_id 999
    entry.user = MagicMock()
    entry.user.id = 444
    entry.created_at = discord.utils.utcnow()

    class AsyncIterator:
        def __init__(self, items):
            self.items = items
        def __aiter__(self):
            return self
        async def __anext__(self):
            if not self.items:
                raise StopAsyncIteration
            return self.items.pop(0)

    guild.audit_logs = MagicMock(return_value=AsyncIterator([entry]))

    # Searching for target_id=999 should return None, NOT entry.user!
    result = await cog._resolve_audit_user(guild, discord.AuditLogAction.channel_delete, target_id=999)
    assert result is None


@pytest.mark.asyncio
async def test_reentrant_lockdown_preserves_initial_state(temp_db):
    bot = MagicMock()
    bot.db_path = temp_db
    cog = AntiRaid(bot)
    cog.db_path = temp_db

    guild = MagicMock(spec=discord.Guild)
    guild.id = 12345
    guild.verification_level = discord.VerificationLevel.medium
    guild.default_role = MagicMock()
    guild.default_role.id = 12345
    guild.edit = AsyncMock()

    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 501
    channel.name = "public"
    channel.overwrites = {}  # Originally no overwrite (inherited)
    channel.overwrites_for = MagicMock(return_value=discord.PermissionOverwrite())
    channel.set_permissions = AsyncMock()
    guild.text_channels = [channel]

    # First lockdown: records existed_prior = 0
    await cog.enable_lockdown(guild)
    states1 = await get_lockdown_states(guild.id, db_path=temp_db)
    assert len(states1) == 1
    assert states1[0]["existed_prior"] == 0

    # Second re-entrant call: must be ignored and not overwrite existed_prior with 1
    channel.overwrites = {guild.default_role: discord.PermissionOverwrite(send_messages=False)}
    channel.set_permissions.reset_mock()
    await cog.enable_lockdown(guild)

    # Should not re-run set_permissions or overwrite database state
    channel.set_permissions.assert_not_called()
    states2 = await get_lockdown_states(guild.id, db_path=temp_db)
    assert states2[0]["existed_prior"] == 0


@pytest.mark.asyncio
async def test_migration_does_not_overwrite_existing_sqlite_data(tmp_path):
    json_path = tmp_path / "guild_config.json"
    db_file = str(tmp_path / "migrated_test.db")
    await init_db(db_file)

    legacy_data = {
        "88888": {
            "log_channel_id": 111,
            "verification_role_id": 222,
        }
    }
    with open(json_path, "w") as f:
        json.dump(legacy_data, f)

    # First migration: imports data and renames JSON to .migrated
    migrated_first = await migrate_from_json(str(json_path), db_path=db_file)
    assert migrated_first == 1

    # Update SQLite with a new value
    await update_guild_config(88888, log_channel_id=999, db_path=db_file)

    # Simulate legacy JSON being re-created
    with open(json_path, "w") as f:
        json.dump(legacy_data, f)

    # Second migration: must NOT overwrite the new SQLite log_channel_id (999) with old (111)
    migrated_second = await migrate_from_json(str(json_path), db_path=db_file)
    assert migrated_second == 0

    cfg = await get_guild_config(88888, db_path=db_file)
    assert cfg["log_channel_id"] == 999
