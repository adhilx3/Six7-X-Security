import datetime

import discord
from discord import app_commands
from discord.ext import commands

from cogs.logging_cog import send_log


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _log_action(self, guild, title, target, moderator, reason, color=discord.Color.red()):
        embed = discord.Embed(title=title, color=color, timestamp=datetime.datetime.utcnow())
        embed.add_field(name="Target", value=f"{target} ({target.id})", inline=False)
        embed.add_field(name="Moderator", value=f"{moderator}", inline=False)
        embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
        await send_log(self.bot, guild, embed)

    @app_commands.command(name="kick", description="Kick a member from the server.")
    @app_commands.checks.has_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = None):
        try:
            await member.kick(reason=reason)
        except discord.Forbidden:
            await interaction.response.send_message("I don't have permission to kick that member.", ephemeral=True)
            return
        await interaction.response.send_message(f"👢 Kicked {member.mention}.")
        await self._log_action(interaction.guild, "👢 Member Kicked", member, interaction.user, reason)

    @app_commands.command(name="ban", description="Ban a member from the server.")
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = None):
        try:
            await member.ban(reason=reason)
        except discord.Forbidden:
            await interaction.response.send_message("I don't have permission to ban that member.", ephemeral=True)
            return
        await interaction.response.send_message(f"🔨 Banned {member.mention}.")
        await self._log_action(interaction.guild, "🔨 Member Banned", member, interaction.user, reason)

    @app_commands.command(name="timeout", description="Timeout (mute) a member for a number of minutes.")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def timeout(self, interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str = None):
        try:
            await member.timeout(
                discord.utils.utcnow() + datetime.timedelta(minutes=minutes), reason=reason
            )
        except discord.Forbidden:
            await interaction.response.send_message("I don't have permission to timeout that member.", ephemeral=True)
            return
        await interaction.response.send_message(f"🔇 Timed out {member.mention} for {minutes} minute(s).")
        await self._log_action(
            interaction.guild, "🔇 Member Timed Out", member, interaction.user,
            f"{reason or 'No reason provided'} ({minutes} min)"
        )

    @app_commands.command(name="warn", description="Warn a member (logged, no other action taken).")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        await interaction.response.send_message(f"⚠️ Warned {member.mention}: {reason}")
        await self._log_action(interaction.guild, "⚠️ Member Warned", member, interaction.user, reason, discord.Color.yellow())
        try:
            await member.send(f"You were warned in **{interaction.guild.name}**: {reason}")
        except discord.Forbidden:
            pass  # user has DMs closed

    @app_commands.command(name="purge", description="Delete a number of recent messages in this channel.")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def purge(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100]):
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.followup.send(f"🧹 Deleted {len(deleted)} message(s).", ephemeral=True)
        embed = discord.Embed(
            title="🧹 Messages Purged",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.utcnow(),
        )
        embed.add_field(name="Channel", value=interaction.channel.mention, inline=False)
        embed.add_field(name="Amount", value=str(len(deleted)), inline=False)
        embed.add_field(name="Moderator", value=str(interaction.user), inline=False)
        await send_log(self.bot, interaction.guild, embed)

    # Friendly error handling for missing permissions on any command in this cog
    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        else:
            await interaction.response.send_message(f"Something went wrong: {error}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
