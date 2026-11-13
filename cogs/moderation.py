import datetime

import discord
from discord import app_commands
from discord.ext import commands

from utils.database import (
    add_warning,
    get_warnings,
    delete_warning,
    clear_warnings,
)
from cogs.logging_cog import send_log


def can_moderate(
    moderator: discord.Member, target: discord.Member, bot_member: discord.Member = None
) -> tuple[bool, str]:
    if target.id == moderator.id:
        return False, "You cannot moderate yourself."

    guild = getattr(moderator, "guild", None)
    if guild and target.id == guild.owner_id:
        return False, "You cannot moderate the server owner."

    if guild and moderator.id != guild.owner_id:
        mod_top = getattr(moderator, "top_role", None)
        target_top = getattr(target, "top_role", None)
        if mod_top and target_top:
            if (
                isinstance(mod_top.position, int)
                and isinstance(target_top.position, int)
                and target_top.position >= mod_top.position
            ):
                return (
                    False,
                    "You cannot moderate this user because their highest role is equal to or higher than yours.",
                )

    if bot_member:
        bot_top = getattr(bot_member, "top_role", None)
        target_top = getattr(target, "top_role", None)
        if bot_top and target_top:
            if (
                isinstance(bot_top.position, int)
                and isinstance(target_top.position, int)
                and target_top.position >= bot_top.position
            ):
                return (
                    False,
                    "I cannot moderate this user because their highest role is equal to or higher than mine.",
                )

    return True, ""


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_path = getattr(bot, "db_path", None)

    async def _log_action(self, guild, title, target, moderator, reason, color=discord.Color.red()):
        embed = discord.Embed(
            title=title, color=color, timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.add_field(name="Target", value=f"{target} ({target.id})", inline=False)
        embed.add_field(name="Moderator", value=f"{moderator}", inline=False)
        embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
        await send_log(self.bot, guild, embed)

    @app_commands.command(name="kick", description="Kick a member from the server.")
    @app_commands.checks.has_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = None):
        allowed, err_msg = can_moderate(interaction.user, member, interaction.guild.me)
        if not allowed:
            await interaction.response.send_message(f"❌ {err_msg}", ephemeral=True)
            return

        try:
            await member.kick(reason=reason)
        except (discord.Forbidden, discord.HTTPException):
            await interaction.response.send_message(
                "❌ Failed to kick member (insufficient bot permissions).", ephemeral=True
            )
            return

        await interaction.response.send_message(f"👢 Kicked {member.mention}.")
        await self._log_action(interaction.guild, "👢 Member Kicked", member, interaction.user, reason)

    @app_commands.command(name="ban", description="Ban a member from the server.")
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        delete_message_days: app_commands.Range[int, 0, 7] = 0,
        reason: str = None,
    ):
        allowed, err_msg = can_moderate(interaction.user, member, interaction.guild.me)
        if not allowed:
            await interaction.response.send_message(f"❌ {err_msg}", ephemeral=True)
            return

        try:
            await member.ban(
                delete_message_seconds=delete_message_days * 86400,
                reason=reason,
            )
        except (discord.Forbidden, discord.HTTPException):
            await interaction.response.send_message(
                "❌ Failed to ban member (insufficient bot permissions).", ephemeral=True
            )
            return

        await interaction.response.send_message(f"🔨 Banned {member.mention}.")
        await self._log_action(interaction.guild, "🔨 Member Banned", member, interaction.user, reason)

    @app_commands.command(name="timeout", description="Timeout (mute) a member for a number of minutes.")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def timeout(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        minutes: app_commands.Range[int, 1, 40320],
        reason: str = None,
    ):
        allowed, err_msg = can_moderate(interaction.user, member, interaction.guild.me)
        if not allowed:
            await interaction.response.send_message(f"❌ {err_msg}", ephemeral=True)
            return

        try:
            until = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=minutes)
            await member.timeout(until, reason=reason)
        except (discord.Forbidden, discord.HTTPException):
            await interaction.response.send_message(
                "❌ Failed to timeout member (insufficient bot permissions).", ephemeral=True
            )
            return

        await interaction.response.send_message(f"🔇 Timed out {member.mention} for {minutes} minute(s).")
        await self._log_action(
            interaction.guild,
            "🔇 Member Timed Out",
            member,
            interaction.user,
            f"{reason or 'No reason provided'} ({minutes} min)",
        )

    @app_commands.command(name="warn", description="Warn a member and save to persistent moderation history.")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        allowed, err_msg = can_moderate(interaction.user, member, interaction.guild.me)
        if not allowed:
            await interaction.response.send_message(f"❌ {err_msg}", ephemeral=True)
            return

        warn_id = await add_warning(
            interaction.guild_id, member.id, interaction.user.id, reason, db_path=self.db_path
        )
        await interaction.response.send_message(f"⚠️ Warned {member.mention} (Case #{warn_id}): {reason}")
        await self._log_action(
            interaction.guild,
            f"⚠️ Member Warned (Case #{warn_id})",
            member,
            interaction.user,
            reason,
            discord.Color.yellow(),
        )
        try:
            await member.send(
                f"You were warned in **{interaction.guild.name}** (Case #{warn_id}): {reason}"
            )
        except (discord.Forbidden, discord.HTTPException):
            pass

    @app_commands.command(name="warnings", description="View warnings for a user or the entire server.")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warnings(self, interaction: discord.Interaction, member: discord.Member = None):
        target_id = member.id if member else None
        warns = await get_warnings(interaction.guild_id, target_id, db_path=self.db_path)

        if not warns:
            target_str = f"for {member.mention}" if member else "in this server"
            await interaction.response.send_message(f"✅ No warnings found {target_str}.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"⚠️ Warnings History ({len(warns)} total)",
            color=discord.Color.orange(),
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )

        for w in warns[:15]:
            created = w["created_at"][:10] if w.get("created_at") else "Unknown"
            embed.add_field(
                name=f"Case #{w['id']} | User: <@{w['user_id']}>",
                value=f"**Mod:** <@{w['moderator_id']}> | **Date:** {created}\n**Reason:** {w['reason']}",
                inline=False,
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="unwarn", description="Delete a warning by case ID.")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def unwarn(self, interaction: discord.Interaction, warning_id: int):
        deleted = await delete_warning(warning_id, db_path=self.db_path)
        if deleted:
            await interaction.response.send_message(f"✅ Warning #{warning_id} deleted.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Warning #{warning_id} not found.", ephemeral=True)

    @app_commands.command(name="clearwarnings", description="Clear all warnings for a user.")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def clearwarnings(self, interaction: discord.Interaction, member: discord.Member):
        allowed, err_msg = can_moderate(interaction.user, member, interaction.guild.me)
        if not allowed:
            await interaction.response.send_message(f"❌ {err_msg}", ephemeral=True)
            return

        cleared = await clear_warnings(interaction.guild_id, member.id, db_path=self.db_path)
        await interaction.response.send_message(
            f"✅ Cleared {cleared} warning(s) for {member.mention}.", ephemeral=True
        )

    @app_commands.command(name="purge", description="Delete a number of recent messages in this channel.")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def purge(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100]):
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.followup.send(f"🧹 Deleted {len(deleted)} message(s).", ephemeral=True)
        embed = discord.Embed(
            title="🧹 Messages Purged",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.add_field(name="Channel", value=interaction.channel.mention, inline=False)
        embed.add_field(name="Amount", value=str(len(deleted)), inline=False)
        embed.add_field(name="Moderator", value=str(interaction.user), inline=False)
        await send_log(self.bot, interaction.guild, embed)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ An error occurred: {error}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
