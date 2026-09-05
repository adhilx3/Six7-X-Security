import discord
from discord import app_commands
from discord.ext import commands

from utils.storage import get_guild_config, update_guild_config


class ConfigCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------- Channel / role setup ----------

    @app_commands.command(name="set-log-channel", description="Set the channel where security logs are sent.")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_log_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        update_guild_config(interaction.guild_id, lambda cfg: cfg.update(log_channel_id=channel.id))
        await interaction.response.send_message(f"✅ Log channel set to {channel.mention}.", ephemeral=True)

    @app_commands.command(name="set-verification-role", description="Set the role given to verified members.")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_verification_role(self, interaction: discord.Interaction, role: discord.Role):
        update_guild_config(interaction.guild_id, lambda cfg: cfg.update(verification_role_id=role.id))
        await interaction.response.send_message(f"✅ Verification role set to {role.mention}.", ephemeral=True)

    # ---------- Automod configuration ----------

    @app_commands.command(name="automod-toggle", description="Enable or disable auto-moderation.")
    @app_commands.checks.has_permissions(administrator=True)
    async def automod_toggle(self, interaction: discord.Interaction, enabled: bool):
        update_guild_config(interaction.guild_id, lambda cfg: cfg["automod"].update(enabled=enabled))
        await interaction.response.send_message(f"✅ Auto-mod {'enabled' if enabled else 'disabled'}.", ephemeral=True)

    @app_commands.command(name="add-banned-word", description="Add a word/phrase to the auto-mod filter.")
    @app_commands.checks.has_permissions(administrator=True)
    async def add_banned_word(self, interaction: discord.Interaction, word: str):
        def _update(cfg):
            if word.lower() not in [w.lower() for w in cfg["automod"]["banned_words"]]:
                cfg["automod"]["banned_words"].append(word)

        update_guild_config(interaction.guild_id, _update)
        await interaction.response.send_message(f"✅ Added `{word}` to the banned word list.", ephemeral=True)

    @app_commands.command(name="remove-banned-word", description="Remove a word from the auto-mod filter.")
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_banned_word(self, interaction: discord.Interaction, word: str):
        def _update(cfg):
            cfg["automod"]["banned_words"] = [
                w for w in cfg["automod"]["banned_words"] if w.lower() != word.lower()
            ]

        update_guild_config(interaction.guild_id, _update)
        await interaction.response.send_message(f"✅ Removed `{word}` from the banned word list.", ephemeral=True)

    @app_commands.command(name="set-max-mentions", description="Set the max mentions allowed per message before action.")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_max_mentions(self, interaction: discord.Interaction, count: app_commands.Range[int, 1, 50]):
        update_guild_config(interaction.guild_id, lambda cfg: cfg["automod"].update(max_mentions=count))
        await interaction.response.send_message(f"✅ Max mentions set to {count}.", ephemeral=True)

    @app_commands.command(name="whitelist-user", description="Exempt a user from auto-mod checks.")
    @app_commands.checks.has_permissions(administrator=True)
    async def whitelist_user(self, interaction: discord.Interaction, user: discord.Member):
        def _update(cfg):
            if user.id not in cfg["whitelist_user_ids"]:
                cfg["whitelist_user_ids"].append(user.id)

        update_guild_config(interaction.guild_id, _update)
        await interaction.response.send_message(f"✅ {user.mention} is now exempt from auto-mod.", ephemeral=True)

    # ---------- Anti-raid configuration ----------

    @app_commands.command(name="antiraid-toggle", description="Enable or disable anti-raid protection.")
    @app_commands.checks.has_permissions(administrator=True)
    async def antiraid_toggle(self, interaction: discord.Interaction, enabled: bool):
        update_guild_config(interaction.guild_id, lambda cfg: cfg["antiraid"].update(enabled=enabled))
        await interaction.response.send_message(f"✅ Anti-raid {'enabled' if enabled else 'disabled'}.", ephemeral=True)

    @app_commands.command(name="set-join-threshold", description="Set how many joins within the time window triggers a raid alert.")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_join_threshold(self, interaction: discord.Interaction, count: app_commands.Range[int, 2, 100], seconds: app_commands.Range[int, 2, 300]):
        def _update(cfg):
            cfg["antiraid"].update(join_threshold=count, join_time_window=seconds)

        update_guild_config(interaction.guild_id, _update)
        await interaction.response.send_message(
            f"✅ Raid alert now triggers at {count} joins within {seconds}s.", ephemeral=True
        )

    @app_commands.command(name="set-min-account-age", description="Set minimum account age (days) required to bypass raid action.")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_min_account_age(self, interaction: discord.Interaction, days: app_commands.Range[int, 0, 365]):
        update_guild_config(interaction.guild_id, lambda cfg: cfg["antiraid"].update(min_account_age_days=days))
        await interaction.response.send_message(f"✅ Minimum account age set to {days} day(s).", ephemeral=True)

    @app_commands.command(name="set-raid-action", description="Set what happens to suspicious new accounts during a raid.")
    @app_commands.choices(action=[
        app_commands.Choice(name="Kick", value="kick"),
        app_commands.Choice(name="Ban", value="ban"),
        app_commands.Choice(name="Log only", value="none"),
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def set_raid_action(self, interaction: discord.Interaction, action: app_commands.Choice[str]):
        update_guild_config(interaction.guild_id, lambda cfg: cfg["antiraid"].update(action_on_raid=action.value))
        await interaction.response.send_message(f"✅ Raid action set to **{action.name}**.", ephemeral=True)

    @app_commands.command(name="lockdown", description="Manually turn server lockdown mode on or off.")
    @app_commands.checks.has_permissions(administrator=True)
    async def lockdown(self, interaction: discord.Interaction, state: bool):
        update_guild_config(interaction.guild_id, lambda cfg: cfg["antiraid"].update(lockdown_active=state))
        await interaction.response.send_message(f"🔒 Lockdown {'enabled' if state else 'disabled'}.", ephemeral=True)

    # ---------- Status ----------

    @app_commands.command(name="security-status", description="View the current security configuration for this server.")
    @app_commands.checks.has_permissions(administrator=True)
    async def security_status(self, interaction: discord.Interaction):
        config = get_guild_config(interaction.guild_id)
        am = config["automod"]
        ar = config["antiraid"]

        embed = discord.Embed(title="🛡️ Security Status", color=discord.Color.blurple())
        embed.add_field(
            name="Auto-Mod",
            value=(
                f"Enabled: **{am['enabled']}**\n"
                f"Banned words: **{len(am['banned_words'])}**\n"
                f"Block invites: **{am['block_invites']}**\n"
                f"Max mentions: **{am['max_mentions']}**\n"
                f"Max caps %: **{am['max_caps_percent']}**\n"
                f"Spam limit: **{am['spam_message_count']} msgs / {am['spam_time_window']}s**"
            ),
            inline=False,
        )
        embed.add_field(
            name="Anti-Raid",
            value=(
                f"Enabled: **{ar['enabled']}**\n"
                f"Join threshold: **{ar['join_threshold']} joins / {ar['join_time_window']}s**\n"
                f"Min account age: **{ar['min_account_age_days']} days**\n"
                f"Raid action: **{ar['action_on_raid']}**\n"
                f"Lockdown active: **{ar['lockdown_active']}**"
            ),
            inline=False,
        )
        log_channel = f"<#{config['log_channel_id']}>" if config["log_channel_id"] else "Not set"
        verify_role = f"<@&{config['verification_role_id']}>" if config["verification_role_id"] else "Not set"
        embed.add_field(name="Log Channel", value=log_channel, inline=True)
        embed.add_field(name="Verification Role", value=verify_role, inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        else:
            await interaction.response.send_message(f"Something went wrong: {error}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ConfigCog(bot))
