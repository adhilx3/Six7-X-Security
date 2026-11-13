import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import discord
from discord.ext import commands

from cogs.antiraid import AntiRaid
from utils.database import (
    init_db,
    get_antiraid_config,
    update_antiraid_config,
    get_lockdown_states,
)


@pytest.fixture
async def temp_db(tmp_path):
    db_file = str(tmp_path / "test_antiraid.db")
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
def antiraid_cog(mock_bot):
    cog = AntiRaid(mock_bot)
    cog.db_path = mock_bot.db_path
    return cog


def create_mock_guild():
    guild = MagicMock(spec=discord.Guild)
    guild.id = 12345
    guild.name = "Raid Test Server"
    guild.default_role = MagicMock(spec=discord.Role)
    guild.default_role.id = 12345
    guild.verification_level = discord.VerificationLevel.medium
    guild.edit = AsyncMock()

    channel1 = MagicMock(spec=discord.TextChannel)
    channel1.id = 101
    channel1.name = "general"
    channel1.overwrites_for = MagicMock(return_value=discord.PermissionOverwrite())
    channel1.overwrites = {}
    channel1.set_permissions = AsyncMock()

    channel2 = MagicMock(spec=discord.TextChannel)
    channel2.id = 102
    channel2.name = "vip"
    existing_ov = discord.PermissionOverwrite(read_messages=True, send_messages=True)
    channel2.overwrites_for = MagicMock(return_value=existing_ov)
    channel2.overwrites = {guild.default_role: existing_ov}
    channel2.set_permissions = AsyncMock()

    guild.text_channels = [channel1, channel2]
    guild.get_channel = MagicMock(side_effect=lambda cid: {101: channel1, 102: channel2}.get(cid))
    return guild, channel1, channel2


@pytest.mark.asyncio
async def test_trigger_lockdown_and_restore(antiraid_cog, temp_db):
    guild, channel1, channel2 = create_mock_guild()

    with patch("cogs.antiraid.send_log", new_callable=AsyncMock) as mock_send_log:
        await antiraid_cog.enable_lockdown(guild)

        # Check DB states
        cfg = await get_antiraid_config(guild.id, db_path=temp_db)
        assert cfg["lockdown_active"] == 1
        assert cfg["original_verification_level"] == "medium"

        states = await get_lockdown_states(guild.id, db_path=temp_db)
        assert len(states) == 2

        # Check channel permissions were set to send_messages=False
        assert channel1.set_permissions.called
        assert channel2.set_permissions.called

        # Now test restore
        await antiraid_cog.disable_lockdown(guild)

        cfg_after = await get_antiraid_config(guild.id, db_path=temp_db)
        assert cfg_after["lockdown_active"] == 0

        states_after = await get_lockdown_states(guild.id, db_path=temp_db)
        assert len(states_after) == 0

        # channel1 had no prior overwrite -> reset to None (preserving category inheritance)
        channel1.set_permissions.assert_called_with(
            guild.default_role, overwrite=None, reason="Anti-Raid: Lockdown lifted - restored inheritance"
        )

        # channel2 had prior overwrite -> restored from pair
        assert channel2.set_permissions.call_count == 2


@pytest.mark.asyncio
async def test_peacetime_young_account_logs_only(antiraid_cog, temp_db):
    guild, _, _ = create_mock_guild()
    member = MagicMock(spec=discord.Member)
    member.guild = guild
    member.id = 555
    member.bot = False
    member.created_at = discord.utils.utcnow()  # 0 days old
    member.kick = AsyncMock()
    member.ban = AsyncMock()

    with patch("cogs.antiraid.send_log", new_callable=AsyncMock) as mock_send_log:
        await antiraid_cog.on_member_join(member)
        mock_send_log.assert_called_once()
        member.kick.assert_not_called()
        member.ban.assert_not_called()


@pytest.mark.asyncio
async def test_lockdown_active_young_account_action_taken(antiraid_cog, temp_db):
    guild, _, _ = create_mock_guild()
    await update_antiraid_config(guild.id, lockdown_active=1, action_on_raid="kick", db_path=temp_db)

    member = MagicMock(spec=discord.Member)
    member.guild = guild
    member.id = 555
    member.bot = False
    member.created_at = discord.utils.utcnow()
    member.kick = AsyncMock()

    with patch("cogs.antiraid.send_log", new_callable=AsyncMock):
        await antiraid_cog.on_member_join(member)
        member.kick.assert_called_once()

