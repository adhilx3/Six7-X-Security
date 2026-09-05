import datetime
from collections import defaultdict, deque

import discord
from discord.ext import commands

from utils.storage import get_guild_config, update_guild_config
from cogs.logging_cog import send_log


class AntiRaid(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # guild_id -> deque of join timestamps
        self.join_history: dict[int, deque] = defaultdict(deque)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        config = get_guild_config(member.guild.id)
        settings = config["antiraid"]
        if not settings["enabled"]:
            return

        now = datetime.datetime.now(datetime.timezone.utc)

        # --- New / suspicious account check ---
        account_age_days = (now - member.created_at).days
        if account_age_days < settings["min_account_age_days"]:
            embed = discord.Embed(
                title="⚠️ New Account Joined",
                description=(
                    f"{member.mention} account is only {account_age_days} day(s) old "
                    f"(minimum allowed: {settings['min_account_age_days']})."
                ),
                color=discord.Color.orange(),
            )
            await send_log(self.bot, member.guild, embed)

            if settings.get("lockdown_active"):
                await self._handle_raid_member(member, settings, "new account during active lockdown")

        # --- Mass join / raid detection ---
        history = self.join_history[member.guild.id]
        history.append(now.timestamp())
        window = settings["join_time_window"]
        while history and now.timestamp() - history[0] > window:
            history.popleft()

        if len(history) >= settings["join_threshold"] and not settings.get("lockdown_active"):
            await self._trigger_lockdown(member.guild, settings, len(history), window)

    async def _handle_raid_member(self, member: discord.Member, settings: dict, reason: str):
        action = settings.get("action_on_raid", "kick")
        try:
            if action == "ban":
                await member.ban(reason=f"Anti-raid: {reason}")
            elif action == "kick":
                await member.kick(reason=f"Anti-raid: {reason}")
            # "none" -> log only, no action taken
        except discord.Forbidden:
            pass

    async def _trigger_lockdown(self, guild: discord.Guild, settings: dict, join_count: int, window: int):
        def _set_lockdown(cfg):
            cfg["antiraid"]["lockdown_active"] = True

        update_guild_config(guild.id, _set_lockdown)

        embed = discord.Embed(
            title="🚨 RAID DETECTED — LOCKDOWN ENABLED",
            description=(
                f"{join_count} members joined within {window} seconds.\n"
                f"New accounts under {settings['min_account_age_days']} days old will now be "
                f"**{settings.get('action_on_raid', 'kick')}ed** automatically.\n\n"
                "Use `/lockdown off` once the raid has passed."
            ),
            color=discord.Color.dark_red(),
        )
        await send_log(self.bot, guild, embed)

        # Optionally tighten verification level automatically
        try:
            await guild.edit(verification_level=discord.VerificationLevel.high)
        except discord.Forbidden:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(AntiRaid(bot))
