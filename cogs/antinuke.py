import datetime
import time
from collections import defaultdict, deque

import discord
from discord.ext import commands

from utils.database import (
    get_antinuke_config,
    is_antinuke_whitelisted,
)
from cogs.logging_cog import send_log

DANGEROUS_PERMISSIONS = {
    "administrator",
    "manage_guild",
    "manage_roles",
    "manage_channels",
    "ban_members",
    "kick_members",
    "manage_webhooks",
    "mention_everyone",
}


class AntiNuke(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_path = getattr(bot, "db_path", None)
        # guild_id -> moderator_id -> category -> deque of timestamps
        self.action_history: dict[int, dict[int, dict[str, deque]]] = defaultdict(
            lambda: defaultdict(lambda: defaultdict(deque))
        )

    async def _is_immune(self, guild: discord.Guild, user_or_member: discord.Member | discord.User) -> bool:
        if user_or_member is None:
            return True
        if user_or_member.id == guild.owner_id:
            return True
        if self.bot.user and user_or_member.id == self.bot.user.id:
            return True
        if await is_antinuke_whitelisted(guild.id, user_or_member.id, db_path=self.db_path):
            return True
        return False

    async def _strip_dangerous_roles(self, guild: discord.Guild, member: discord.Member, reason: str):
        if not hasattr(member, "roles") or not member.roles:
            return
        if (
            guild.me
            and hasattr(guild.me, "top_role")
            and hasattr(member, "top_role")
            and isinstance(guild.me.top_role.position, int)
            and isinstance(member.top_role.position, int)
            and guild.me.top_role.position <= member.top_role.position
        ):
            return

        roles_to_remove = []
        for role in member.roles:
            if role.id == guild.id:
                continue
            if callable(getattr(role, "is_default", None)) and role.is_default() is True:
                continue
            perms = getattr(role, "permissions", None)
            if not perms:
                continue
            for perm_name in DANGEROUS_PERMISSIONS:
                if getattr(perms, perm_name, False) is True:
                    roles_to_remove.append(role)
                    break

        if roles_to_remove:
            try:
                await member.remove_roles(*roles_to_remove, reason=reason)
            except (discord.Forbidden, discord.HTTPException):
                pass

    async def _check_and_punish(
        self, guild: discord.Guild, moderator: discord.Member | discord.User, category: str, detail: str
    ) -> bool:
        if await self._is_immune(guild, moderator):
            return False

        cfg = await get_antinuke_config(guild.id, db_path=self.db_path)
        if not cfg["enabled"]:
            return False

        now = time.time()
        window = cfg.get("action_window_seconds", 10)
        history = self.action_history[guild.id][moderator.id][category]
        history.append(now)

        while history and now - history[0] > window:
            history.popleft()

        threshold = cfg.get(f"max_{category}_actions", 3)
        if len(history) < threshold:
            return False

        history.clear()
        punishment = cfg.get("punishment", "strip_roles")
        reason = f"Anti-Nuke: Exceeded {category} action threshold ({threshold} in {window}s)"

        member = moderator if isinstance(moderator, discord.Member) else (
            guild.get_member(moderator.id) if hasattr(guild, "get_member") else None
        )

        action_taken = "None"
        if member:
            try:
                if punishment == "ban":
                    await member.ban(reason=reason)
                    action_taken = "Banned"
                elif punishment == "kick":
                    await member.kick(reason=reason)
                    action_taken = "Kicked"
                else:
                    await self._strip_dangerous_roles(guild, member, reason)
                    action_taken = "Stripped Dangerous Roles"
            except (discord.Forbidden, discord.HTTPException):
                action_taken = "Failed (Insufficient bot permissions)"

        embed = discord.Embed(
            title="🚨 ANTI-NUKE TRIGGERED",
            description=f"Destructive rate limit exceeded by {moderator.mention if hasattr(moderator, 'mention') else moderator}.",
            color=discord.Color.dark_red(),
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.add_field(name="Offender", value=f"{moderator} ({moderator.id})", inline=False)
        embed.add_field(name="Category", value=category.capitalize(), inline=True)
        embed.add_field(name="Action Taken", value=action_taken, inline=True)
        embed.add_field(name="Details", value=detail, inline=False)

        await send_log(self.bot, guild, embed)

        # Notify guild owner via DM
        try:
            if guild.owner:
                await guild.owner.send(
                    f"⚠️ **URGENT**: Anti-Nuke triggered in **{guild.name}**!\n"
                    f"Offender: {moderator} ({moderator.id})\n"
                    f"Category: {category}\n"
                    f"Punishment: {action_taken}\n"
                    f"Details: {detail}"
                )
        except (discord.Forbidden, discord.HTTPException):
            pass

        return True

    async def _resolve_audit_user(
        self, guild: discord.Guild, action: discord.AuditLogAction, target_id: int = None
    ) -> discord.Member | discord.User | None:
        if not hasattr(guild, "audit_logs"):
            return None
        now_ts = datetime.datetime.now(datetime.timezone.utc).timestamp()
        try:
            async for entry in guild.audit_logs(action=action, limit=5):
                entry_ts = getattr(entry, "created_at", None)
                if entry_ts and abs(now_ts - entry_ts.timestamp()) > 10:
                    continue
                if target_id is not None and getattr(entry, "target", None):
                    if entry.target.id == target_id:
                        return entry.user
                else:
                    return entry.user
        except (discord.Forbidden, discord.HTTPException):
            return None
        return None

    # ---------- Event Listeners ----------

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        guild = channel.guild
        mod = await self._resolve_audit_user(guild, discord.AuditLogAction.channel_delete, channel.id)
        if mod:
            await self._check_and_punish(guild, mod, "channel", f"Deleted channel #{channel.name}")

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        guild = channel.guild
        mod = await self._resolve_audit_user(guild, discord.AuditLogAction.channel_create, channel.id)
        if mod:
            await self._check_and_punish(guild, mod, "channel", f"Created channel #{channel.name}")

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        guild = role.guild
        mod = await self._resolve_audit_user(guild, discord.AuditLogAction.role_delete, role.id)
        if mod:
            await self._check_and_punish(guild, mod, "role", f"Deleted role @{role.name}")

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        guild = role.guild
        mod = await self._resolve_audit_user(guild, discord.AuditLogAction.role_create, role.id)
        if mod:
            await self._check_and_punish(guild, mod, "role", f"Created role @{role.name}")

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User | discord.Member):
        mod = await self._resolve_audit_user(guild, discord.AuditLogAction.ban, user.id)
        if mod:
            await self._check_and_punish(guild, mod, "member", f"Banned user {user}")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        guild = member.guild
        mod = await self._resolve_audit_user(guild, discord.AuditLogAction.kick, member.id)
        if mod:
            await self._check_and_punish(guild, mod, "member", f"Kicked member {member}")

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.abc.GuildChannel):
        guild = channel.guild
        mod = await self._resolve_audit_user(guild, discord.AuditLogAction.webhook_create)
        if not mod:
            mod = await self._resolve_audit_user(guild, discord.AuditLogAction.webhook_delete)
        if not mod:
            mod = await self._resolve_audit_user(guild, discord.AuditLogAction.webhook_update)
        if mod:
            await self._check_and_punish(guild, mod, "webhook", f"Modified webhooks in #{channel.name}")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if not member.bot:
            return

        guild = member.guild
        inviter = None
        if hasattr(guild, "audit_logs"):
            try:
                async for entry in guild.audit_logs(action=discord.AuditLogAction.bot_add, limit=5):
                    if entry.target and entry.target.id == member.id:
                        inviter = entry.user
                        break
            except (discord.Forbidden, discord.HTTPException):
                inviter = None

        if inviter and await self._is_immune(guild, inviter):
            return

        cfg = await get_antinuke_config(guild.id, db_path=self.db_path)
        if not cfg["enabled"]:
            return

        # Kick unauthorized bot
        try:
            await member.kick(reason="Anti-Nuke: Unauthorized bot addition")
        except (discord.Forbidden, discord.HTTPException):
            pass

        # Punish inviter
        inviter_member = guild.get_member(inviter.id) if (inviter and hasattr(guild, "get_member")) else inviter
        if inviter_member:
            await self._strip_dangerous_roles(guild, inviter_member, "Anti-Nuke: Invited unauthorized bot")

        embed = discord.Embed(
            title="🚨 UNAUTHORIZED BOT BLOCKED",
            description=f"Bot {member.mention} was added without authorization and kicked.",
            color=discord.Color.red(),
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.add_field(name="Bot", value=f"{member} ({member.id})", inline=True)
        if inviter:
            embed.add_field(name="Invited By", value=f"{inviter} ({inviter.id})", inline=True)
        await send_log(self.bot, guild, embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(AntiNuke(bot))
