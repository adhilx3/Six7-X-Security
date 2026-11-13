import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import discord
from discord.ext import commands

from cogs.antinuke import AntiNuke, DANGEROUS_PERMISSIONS
from utils.database import init_db, update_antinuke_config, add_antinuke_whitelist


@pytest.fixture
async def temp_db(tmp_path):
    db_file = str(tmp_path / "test_antinuke.db")
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
def antinuke_cog(mock_bot):
    cog = AntiNuke(mock_bot)
    cog.db_path = mock_bot.db_path
    return cog


def create_mock_guild(owner_id=999999):
    guild = MagicMock(spec=discord.Guild)
    guild.id = 12345
    guild.name = "Security Test Server"
    guild.owner_id = owner_id
    guild.owner = MagicMock(spec=discord.Member)
    guild.owner.id = owner_id
    guild.owner.send = AsyncMock()
    guild.me = MagicMock(spec=discord.Member)
    guild.me.top_role = MagicMock(spec=discord.Role)
    guild.me.top_role.position = 100
    guild.audit_logs = MagicMock()
    return guild


def create_mock_member(user_id=222222, guild=None, top_role_pos=50):
    member = MagicMock(spec=discord.Member)
    member.id = user_id
    member.name = f"User_{user_id}"
    member.mention = f"<@{user_id}>"
    member.bot = False
    member.guild = guild
    member.top_role = MagicMock(spec=discord.Role)
    member.top_role.position = top_role_pos
    member.roles = []
    member.remove_roles = AsyncMock()
    member.kick = AsyncMock()
    member.ban = AsyncMock()
    return member


@pytest.mark.asyncio
async def test_owner_is_immune(antinuke_cog):
    guild = create_mock_guild(owner_id=999)
    owner = create_mock_member(user_id=999, guild=guild)

    is_immune = await antinuke_cog._is_immune(guild, owner)
    assert is_immune is True


@pytest.mark.asyncio
async def test_whitelisted_user_is_immune(antinuke_cog, temp_db):
    guild = create_mock_guild(owner_id=999)
    trusted = create_mock_member(user_id=888, guild=guild)

    assert await antinuke_cog._is_immune(guild, trusted) is False

    await add_antinuke_whitelist(guild.id, trusted.id, reason="Trusted mod", added_by=999, db_path=temp_db)
    assert await antinuke_cog._is_immune(guild, trusted) is True


@pytest.mark.asyncio
async def test_rate_limit_and_strip_roles_punishment(antinuke_cog, temp_db):
    guild = create_mock_guild(owner_id=999)
    rogue_mod = create_mock_member(user_id=555, guild=guild, top_role_pos=50)

    admin_role = MagicMock(spec=discord.Role)
    admin_role.name = "Admin"
    admin_role.permissions = discord.Permissions(administrator=True)

    normal_role = MagicMock(spec=discord.Role)
    normal_role.name = "Member"
    normal_role.permissions = discord.Permissions(read_messages=True)

    rogue_mod.roles = [admin_role, normal_role]

    await update_antinuke_config(
        guild.id,
        enabled=1,
        max_channel_actions=2,
        action_window_seconds=10,
        punishment="strip_roles",
        db_path=temp_db,
    )

    with patch("cogs.antinuke.send_log", new_callable=AsyncMock) as mock_send_log:
        # First action: threshold not yet breached
        triggered_1 = await antinuke_cog._check_and_punish(guild, rogue_mod, "channel", "Deleted channel #general")
        assert triggered_1 is False
        rogue_mod.remove_roles.assert_not_called()

        # Second action: threshold reached (>= 2)
        triggered_2 = await antinuke_cog._check_and_punish(guild, rogue_mod, "channel", "Deleted channel #chat")
        assert triggered_2 is True
        rogue_mod.remove_roles.assert_called_once_with(admin_role, reason="Anti-Nuke: Exceeded channel action threshold (2 in 10s)")
        mock_send_log.assert_called_once()


@pytest.mark.asyncio
async def test_ban_punishment(antinuke_cog, temp_db):
    guild = create_mock_guild(owner_id=999)
    rogue_mod = create_mock_member(user_id=555, guild=guild, top_role_pos=50)

    await update_antinuke_config(
        guild.id,
        enabled=1,
        max_member_actions=1,
        action_window_seconds=10,
        punishment="ban",
        db_path=temp_db,
    )

    with patch("cogs.antinuke.send_log", new_callable=AsyncMock):
        triggered = await antinuke_cog._check_and_punish(guild, rogue_mod, "member", "Mass ban detected")
        assert triggered is True
        rogue_mod.ban.assert_called_once()


@pytest.mark.asyncio
async def test_unauthorized_bot_join_blocked(antinuke_cog, temp_db):
    guild = create_mock_guild(owner_id=999)
    bot_member = create_mock_member(user_id=7777, guild=guild)
    bot_member.bot = True

    inviter = create_mock_member(user_id=4444, guild=guild)
    admin_role = MagicMock(spec=discord.Role)
    admin_role.permissions = discord.Permissions(administrator=True)
    inviter.roles = [admin_role]

    guild.get_member = MagicMock(return_value=inviter)

    mock_entry = MagicMock()
    mock_entry.target.id = bot_member.id
    mock_entry.user = inviter
    mock_entry.user.id = inviter.id

    class AsyncIterator:
        def __init__(self, items):
            self.items = items
        def __aiter__(self):
            return self
        async def __anext__(self):
            if not self.items:
                raise StopAsyncIteration
            return self.items.pop(0)

    guild.audit_logs = MagicMock(return_value=AsyncIterator([mock_entry]))

    with patch("cogs.antinuke.send_log", new_callable=AsyncMock) as mock_send_log:
        await antinuke_cog.on_member_join(bot_member)
        bot_member.kick.assert_called_once_with(reason="Anti-Nuke: Unauthorized bot addition")
        inviter.remove_roles.assert_called_once()
        mock_send_log.assert_called_once()
