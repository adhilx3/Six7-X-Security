import datetime
import time
from collections import defaultdict, deque

import discord
from discord.ext import commands

from utils.database import (
    get_antiraid_config,
    update_antiraid_config,
    save_channel_lockdown_state,
    get_lockdown_states,
    clear_lockdown_states,
)
from cogs.logging_cog import send_log


class AntiRaid(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_path = getattr(bot, "db_path", None)
        # guild_id -> deque of join timestamps
        self.join_history: dict[int, deque] = defaultdict(deque)

    async def enable_lockdown(self, guild: discord.Guild, reason: str = "Anti-Raid lockdown"):
        cfg = await get_antiraid_config(guild.id, db_path=self.db_path)
        orig_vl = getattr(guild.verification_level, "name", str(guild.verification_level))
        await update_antiraid_config(
            guild.id,
            lockdown_active=1,
            original_verification_level=orig_vl,
            db_path=self.db_path,
        )

        channels = getattr(guild, "text_channels", [])
        for channel in channels:
            try:
                has_prior = guild.default_role in getattr(channel, "overwrites", {})
                ov = channel.overwrites_for(guild.default_role)
                if hasattr(ov, "pair"):
                    allow_bits = ov.pair()[0].value
                    deny_bits = ov.pair()[1].value
                else:
                    allow_bits, deny_bits = 0, 0

                await save_channel_lockdown_state(
                    guild.id, channel.id, has_prior, allow_bits, deny_bits, db_path=self.db_path
                )
                ov.send_messages = False
                await channel.set_permissions(
                    guild.default_role, overwrite=ov, reason="Anti-Raid: Server lockdown enabled"
                )
            except (discord.Forbidden, discord.HTTPException):
                pass

        try:
            await guild.edit(verification_level=discord.VerificationLevel.high)
        except (discord.Forbidden, discord.HTTPException):
            pass

        embed = discord.Embed(
            title="🚨 RAID DETECTED — LOCKDOWN ENABLED",
            description=(
                f"Reason: {reason}\n"
                f"Public text channels have been locked.\n"
                f"New accounts under {cfg['min_account_age_days']} days old will now be "
                f"**{cfg.get('action_on_raid', 'kick')}ed** automatically.\n\n"
                "Use `/lockdown state:false` once the raid has passed."
            ),
            color=discord.Color.dark_red(),
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        await send_log(self.bot, guild, embed)

    async def disable_lockdown(self, guild: discord.Guild):
        states = await get_lockdown_states(guild.id, db_path=self.db_path)
        for state in states:
            channel = guild.get_channel(state["channel_id"]) if hasattr(guild, "get_channel") else None
            if not channel:
                continue
            try:
                if state["existed_prior"] == 0:
                    await channel.set_permissions(
                        guild.default_role,
                        overwrite=None,
                        reason="Anti-Raid: Lockdown lifted - restored inheritance",
                    )
                else:
                    allow = discord.Permissions(state["allow_bits"])
                    deny = discord.Permissions(state["deny_bits"])
                    restored = discord.PermissionOverwrite.from_pair(allow, deny)
                    await channel.set_permissions(
                        guild.default_role,
                        overwrite=restored,
                        reason="Anti-Raid: Lockdown lifted - restored permissions",
                    )
            except (discord.Forbidden, discord.HTTPException):
                pass

        await clear_lockdown_states(guild.id, db_path=self.db_path)

        cfg = await get_antiraid_config(guild.id, db_path=self.db_path)
        orig_vl_name = cfg.get("original_verification_level")
        if orig_vl_name:
            lvl = getattr(discord.VerificationLevel, orig_vl_name, None)
            if lvl:
                try:
                    await guild.edit(verification_level=lvl)
                except (discord.Forbidden, discord.HTTPException):
                    pass

        await update_antiraid_config(
            guild.id,
            lockdown_active=0,
            original_verification_level=None,
            db_path=self.db_path,
        )

        embed = discord.Embed(
            title="🔓 LOCKDOWN LIFTED",
            description="Channel permissions and server verification levels have been restored to their original state.",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        await send_log(self.bot, guild, embed)

    async def _handle_raid_member(self, member: discord.Member, settings: dict, reason: str):
        action = settings.get("action_on_raid", "kick")
        try:
            if action == "ban":
                await member.ban(reason=f"Anti-raid: {reason}")
            elif action == "kick":
                await member.kick(reason=f"Anti-raid: {reason}")
        except (discord.Forbidden, discord.HTTPException):
            pass

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot or member.guild is None:
            return

        cfg = await get_antiraid_config(member.guild.id, db_path=self.db_path)
        if not cfg["enabled"]:
            return

        now = datetime.datetime.now(datetime.timezone.utc)
        account_age_days = (now - member.created_at).days

        # --- New / suspicious account check ---
        if account_age_days < cfg["min_account_age_days"]:
            embed = discord.Embed(
                title="⚠️ New Account Joined",
                description=(
                    f"{member.mention} account is only {account_age_days} day(s) old "
                    f"(minimum allowed: {cfg['min_account_age_days']})."
                ),
                color=discord.Color.orange(),
                timestamp=datetime.datetime.now(datetime.timezone.utc),
            )
            await send_log(self.bot, member.guild, embed)

            if cfg.get("lockdown_active"):
                await self._handle_raid_member(member, cfg, "new account during active lockdown")
                return

        # --- Mass join / raid detection ---
        history = self.join_history[member.guild.id]
        now_ts = now.timestamp()
        history.append(now_ts)
        window = cfg["join_time_window"]
        while history and now_ts - history[0] > window:
            history.popleft()

        if len(history) >= cfg["join_threshold"] and not cfg.get("lockdown_active"):
            await self.enable_lockdown(
                member.guild,
                reason=f"{len(history)} members joined within {window} seconds.",
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(AntiRaid(bot))
