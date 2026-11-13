import discord
from discord import app_commands
from discord.ext import commands

from utils.database import (
    get_guild_config,
    update_guild_config,
    get_automod_config,
    update_automod_config,
    get_antiraid_config,
    update_antiraid_config,
    get_antinuke_config,
    update_antinuke_config,
    add_antinuke_whitelist,
    remove_antinuke_whitelist,
    get_antinuke_whitelist,
)


class ConfigCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_path = getattr(bot, "db_path", None)

    # ---------- Channel / Role Setup ----------

    @app_commands.command(name="set-log-channel", description="Set the channel where security logs are sent.")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_log_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await update_guild_config(interaction.guild_id, log_channel_id=channel.id, db_path=self.db_path)
        await interaction.response.send_message(f"✅ Log channel set to {channel.mention}.", ephemeral=True)

    # ---------- Anti-Nuke Configuration ----------

    @app_commands.command(name="antinuke-toggle", description="Enable or disable anti-nuke protection.")
    @app_commands.checks.has_permissions(administrator=True)
    async def antinuke_toggle(self, interaction: discord.Interaction, enabled: bool):
        await update_antinuke_config(interaction.guild_id, enabled=1 if enabled else 0, db_path=self.db_path)
        await interaction.response.send_message(
            f"🛡️ Anti-Nuke is now **{'enabled' if enabled else 'disabled'}**.", ephemeral=True
        )

    @app_commands.command(name="antinuke-config", description="Configure anti-nuke action thresholds and punishment.")
    @app_commands.choices(punishment=[
        app_commands.Choice(name="Strip Dangerous Roles", value="strip_roles"),
        app_commands.Choice(name="Ban Offender", value="ban"),
        app_commands.Choice(name="Kick Offender", value="kick"),
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def antinuke_config(
        self,
        interaction: discord.Interaction,
        window_seconds: app_commands.Range[int, 2, 60] = 10,
        channel_actions: app_commands.Range[int, 1, 20] = 3,
        role_actions: app_commands.Range[int, 1, 20] = 3,
        member_actions: app_commands.Range[int, 1, 20] = 3,
        webhook_actions: app_commands.Range[int, 1, 20] = 3,
        punishment: app_commands.Choice[str] = None,
    ):
        kwargs = {
            "action_window_seconds": window_seconds,
            "max_channel_actions": channel_actions,
            "max_role_actions": role_actions,
            "max_member_actions": member_actions,
            "max_webhook_actions": webhook_actions,
        }
        if punishment:
            kwargs["punishment"] = punishment.value
        await update_antinuke_config(interaction.guild_id, db_path=self.db_path, **kwargs)
        punish_name = punishment.name if punishment else "unchanged"
        await interaction.response.send_message(
            f"✅ Anti-Nuke settings updated:\n"
            f"- Action window: **{window_seconds}s**\n"
            f"- Channel limits: **{channel_actions} actions**\n"
            f"- Role limits: **{role_actions} actions**\n"
            f"- Member kick/ban limits: **{member_actions} actions**\n"
            f"- Webhook limits: **{webhook_actions} actions**\n"
            f"- Punishment: **{punish_name}**",
            ephemeral=True,
        )

    @app_commands.command(name="antinuke-whitelist-add", description="Add a trusted user or bot to Anti-Nuke immunity.")
    @app_commands.checks.has_permissions(administrator=True)
    async def antinuke_whitelist_add(
        self, interaction: discord.Interaction, target: discord.User, reason: str = "Authorized Staff"
    ):
        added_by = getattr(interaction.user, "id", 0)
        if not isinstance(added_by, int):
            added_by = 0
        await add_antinuke_whitelist(
            interaction.guild_id, target.id, reason=reason, added_by=added_by, db_path=self.db_path
        )
        await interaction.response.send_message(
            f"✅ {target.mention} is now whitelisted from Anti-Nuke actions (`{reason}`).",
            ephemeral=True,
        )

    @app_commands.command(name="antinuke-whitelist-remove", description="Remove a user or bot from Anti-Nuke immunity.")
    @app_commands.checks.has_permissions(administrator=True)
    async def antinuke_whitelist_remove(self, interaction: discord.Interaction, target: discord.User):
        removed = await remove_antinuke_whitelist(interaction.guild_id, target.id, db_path=self.db_path)
        if removed:
            await interaction.response.send_message(
                f"✅ Removed {target.mention} from Anti-Nuke whitelist.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"❌ {target.mention} was not found on the Anti-Nuke whitelist.", ephemeral=True
            )

    @app_commands.command(name="antinuke-whitelist-list", description="List all Anti-Nuke whitelisted accounts.")
    @app_commands.checks.has_permissions(administrator=True)
    async def antinuke_whitelist_list(self, interaction: discord.Interaction):
        wl = await get_antinuke_whitelist(interaction.guild_id, db_path=self.db_path)
        if not wl:
            await interaction.response.send_message("ℹ️ No whitelisted users/bots configured.", ephemeral=True)
            return

        embed = discord.Embed(
            title="🛡️ Anti-Nuke Whitelist",
            color=discord.Color.blurple(),
        )
        for entry in wl[:25]:
            embed.add_field(
                name=f"User ID: {entry['target_id']}",
                value=f"<@{entry['target_id']}> | Reason: {entry.get('reason', 'None')}",
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ---------- Automod Configuration ----------

    @app_commands.command(name="automod-toggle", description="Enable or disable auto-moderation.")
    @app_commands.checks.has_permissions(administrator=True)
    async def automod_toggle(self, interaction: discord.Interaction, enabled: bool):
        await update_automod_config(interaction.guild_id, enabled=1 if enabled else 0, db_path=self.db_path)
        await interaction.response.send_message(
            f"✅ Auto-mod {'enabled' if enabled else 'disabled'}.", ephemeral=True
        )

    @app_commands.command(name="add-banned-word", description="Add a word/phrase to the auto-mod filter.")
    @app_commands.checks.has_permissions(administrator=True)
    async def add_banned_word(self, interaction: discord.Interaction, word: str):
        cfg = await get_automod_config(interaction.guild_id, db_path=self.db_path)
        words = list(cfg.get("banned_words", []))
        if word.lower() not in [w.lower() for w in words]:
            words.append(word)
            await update_automod_config(interaction.guild_id, banned_words=words, db_path=self.db_path)
        await interaction.response.send_message(f"✅ Added `{word}` to the banned word filter.", ephemeral=True)

    @app_commands.command(name="remove-banned-word", description="Remove a word from the auto-mod filter.")
    @app_commands.checks.has_permissions(administrator=True)
    async def remove_banned_word(self, interaction: discord.Interaction, word: str):
        cfg = await get_automod_config(interaction.guild_id, db_path=self.db_path)
        words = [w for w in cfg.get("banned_words", []) if w.lower() != word.lower()]
        await update_automod_config(interaction.guild_id, banned_words=words, db_path=self.db_path)
        await interaction.response.send_message(f"✅ Removed `{word}` from the banned word filter.", ephemeral=True)

    @app_commands.command(name="set-max-mentions", description="Set max mentions allowed per message.")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_max_mentions(self, interaction: discord.Interaction, count: app_commands.Range[int, 1, 50]):
        await update_automod_config(interaction.guild_id, max_mentions=count, db_path=self.db_path)
        await interaction.response.send_message(f"✅ Max mentions set to {count}.", ephemeral=True)

    @app_commands.command(name="whitelist-user", description="Exempt a user from auto-mod chat checks.")
    @app_commands.checks.has_permissions(administrator=True)
    async def whitelist_user(self, interaction: discord.Interaction, user: discord.Member):
        cfg = await get_automod_config(interaction.guild_id, db_path=self.db_path)
        users = list(cfg.get("whitelist_user_ids", []))
        if user.id not in users:
            users.append(user.id)
            await update_automod_config(interaction.guild_id, whitelist_user_ids=users, db_path=self.db_path)
        await interaction.response.send_message(f"✅ {user.mention} is now exempt from AutoMod.", ephemeral=True)

    @app_commands.command(name="whitelist-role", description="Exempt a role from auto-mod chat checks.")
    @app_commands.checks.has_permissions(administrator=True)
    async def whitelist_role(self, interaction: discord.Interaction, role: discord.Role):
        cfg = await get_automod_config(interaction.guild_id, db_path=self.db_path)
        roles = list(cfg.get("whitelist_role_ids", []))
        if role.id not in roles:
            roles.append(role.id)
            await update_automod_config(interaction.guild_id, whitelist_role_ids=roles, db_path=self.db_path)
        await interaction.response.send_message(f"✅ Role {role.mention} is now exempt from AutoMod.", ephemeral=True)

    @app_commands.command(name="automod-scam-toggle", description="Enable or disable phishing / scam link blocking.")
    @app_commands.checks.has_permissions(administrator=True)
    async def automod_scam_toggle(self, interaction: discord.Interaction, enabled: bool):
        await update_automod_config(interaction.guild_id, block_scams=1 if enabled else 0, db_path=self.db_path)
        await interaction.response.send_message(
            f"✅ Scam link blocking is now **{'enabled' if enabled else 'disabled'}**.", ephemeral=True
        )

    @app_commands.command(name="automod-attachments-toggle", description="Enable or disable dangerous file blocking.")
    @app_commands.checks.has_permissions(administrator=True)
    async def automod_attachments_toggle(self, interaction: discord.Interaction, enabled: bool):
        await update_automod_config(interaction.guild_id, block_attachments=1 if enabled else 0, db_path=self.db_path)
        await interaction.response.send_message(
            f"✅ Dangerous attachment blocking is now **{'enabled' if enabled else 'disabled'}**.", ephemeral=True
        )

    # ---------- Anti-Raid Configuration ----------

    @app_commands.command(name="antiraid-toggle", description="Enable or disable anti-raid protection.")
    @app_commands.checks.has_permissions(administrator=True)
    async def antiraid_toggle(self, interaction: discord.Interaction, enabled: bool):
        await update_antiraid_config(interaction.guild_id, enabled=1 if enabled else 0, db_path=self.db_path)
        await interaction.response.send_message(
            f"✅ Anti-raid {'enabled' if enabled else 'disabled'}.", ephemeral=True
        )

    @app_commands.command(name="set-join-threshold", description="Set join count and time window for raid alerts.")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_join_threshold(
        self, interaction: discord.Interaction, count: app_commands.Range[int, 2, 100], seconds: app_commands.Range[int, 2, 300]
    ):
        await update_antiraid_config(
            interaction.guild_id, join_threshold=count, join_time_window=seconds, db_path=self.db_path
        )
        await interaction.response.send_message(
            f"✅ Raid alert now triggers at {count} joins within {seconds}s.", ephemeral=True
        )

    @app_commands.command(name="set-min-account-age", description="Minimum account age (days) for raid flags/actions.")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_min_account_age(self, interaction: discord.Interaction, days: app_commands.Range[int, 0, 365]):
        await update_antiraid_config(interaction.guild_id, min_account_age_days=days, db_path=self.db_path)
        await interaction.response.send_message(f"✅ Minimum account age set to {days} day(s).", ephemeral=True)

    @app_commands.command(name="set-raid-action", description="Set action taken against suspicious joins during raids.")
    @app_commands.choices(action=[
        app_commands.Choice(name="Kick", value="kick"),
        app_commands.Choice(name="Ban", value="ban"),
        app_commands.Choice(name="Log only", value="none"),
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def set_raid_action(self, interaction: discord.Interaction, action: app_commands.Choice[str]):
        await update_antiraid_config(interaction.guild_id, action_on_raid=action.value, db_path=self.db_path)
        await interaction.response.send_message(f"✅ Raid action set to **{action.name}**.", ephemeral=True)

    @app_commands.command(name="lockdown", description="Manually enable or disable server lockdown mode.")
    @app_commands.checks.has_permissions(administrator=True)
    async def lockdown(self, interaction: discord.Interaction, state: bool):
        antiraid_cog = self.bot.get_cog("AntiRaid")
        if antiraid_cog:
            if state:
                await antiraid_cog.enable_lockdown(interaction.guild, reason="Manual lockdown via /lockdown")
            else:
                await antiraid_cog.disable_lockdown(interaction.guild)
        else:
            await update_antiraid_config(interaction.guild_id, lockdown_active=1 if state else 0, db_path=self.db_path)

        await interaction.response.send_message(
            f"🔒 Lockdown mode **{'enabled' if state else 'disabled'}**.", ephemeral=True
        )

    # ---------- Status Overview ----------

    @app_commands.command(name="security-status", description="View the current security configuration for this server.")
    @app_commands.checks.has_permissions(administrator=True)
    async def security_status(self, interaction: discord.Interaction):
        g_cfg = await get_guild_config(interaction.guild_id, db_path=self.db_path)
        an = await get_antinuke_config(interaction.guild_id, db_path=self.db_path)
        ar = await get_antiraid_config(interaction.guild_id, db_path=self.db_path)
        am = await get_automod_config(interaction.guild_id, db_path=self.db_path)
        wl = await get_antinuke_whitelist(interaction.guild_id, db_path=self.db_path)

        embed = discord.Embed(title="🛡️ Security Status Overview", color=discord.Color.blurple())

        embed.add_field(
            name="🛡️ Anti-Nuke",
            value=(
                f"Enabled: **{'Yes' if an['enabled'] else 'No'}**\n"
                f"Punishment: **{an.get('punishment', 'strip_roles')}**\n"
                f"Channel limits: **{an.get('max_channel_actions', 3)} / {an.get('action_window_seconds', 10)}s**\n"
                f"Role limits: **{an.get('max_role_actions', 3)} / {an.get('action_window_seconds', 10)}s**\n"
                f"Member limits: **{an.get('max_member_actions', 3)} / {an.get('action_window_seconds', 10)}s**\n"
                f"Whitelisted accounts: **{len(wl)}**"
            ),
            inline=False,
        )

        embed.add_field(
            name="🚨 Anti-Raid",
            value=(
                f"Enabled: **{'Yes' if ar['enabled'] else 'No'}**\n"
                f"Threshold: **{ar['join_threshold']} joins / {ar['join_time_window']}s**\n"
                f"Min account age: **{ar['min_account_age_days']} days**\n"
                f"Raid action: **{ar['action_on_raid']}**\n"
                f"Lockdown active: **{'Yes' if ar['lockdown_active'] else 'No'}**"
            ),
            inline=False,
        )

        embed.add_field(
            name="🤖 Auto-Mod",
            value=(
                f"Enabled: **{'Yes' if am['enabled'] else 'No'}**\n"
                f"Banned words: **{len(am.get('banned_words', []))}**\n"
                f"Block scams: **{'Yes' if am.get('block_scams', 1) else 'No'}**\n"
                f"Block files: **{'Yes' if am.get('block_attachments', 1) else 'No'}**\n"
                f"Block duplicates: **{'Yes' if am.get('block_duplicates', 1) else 'No'}**\n"
                f"Max mentions: **{am.get('max_mentions', 5)}**\n"
                f"Spam limit: **{am.get('spam_message_count', 5)} msgs / {am.get('spam_time_window', 5)}s**"
            ),
            inline=False,
        )

        log_ch = f"<#{g_cfg['log_channel_id']}>" if g_cfg.get("log_channel_id") else "Not set"
        verify_r = f"<@&{g_cfg['verification_role_id']}>" if g_cfg.get("verification_role_id") else "Not set"
        unverify_r = f"<@&{g_cfg['unverified_role_id']}>" if g_cfg.get("unverified_role_id") else "Not set"
        v_mode = "Captcha Challenge" if g_cfg.get("verification_type") == "captcha" else "Button Click"

        embed.add_field(
            name="🔒 Verification & Logs",
            value=(
                f"Mode: **{v_mode}**\n"
                f"Log channel: {log_ch}\n"
                f"Verified role: {verify_r}\n"
                f"Unverified role: {unverify_r}"
            ),
            inline=False,
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ An error occurred: {error}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ConfigCog(bot))
