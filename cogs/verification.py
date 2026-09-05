import discord
from discord import app_commands
from discord.ext import commands

from utils.storage import get_guild_config
from cogs.logging_cog import send_log


class VerifyView(discord.ui.View):
    """Persistent view - registered once in setup_hook so the button keeps working after restarts."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Verify",
        style=discord.ButtonStyle.success,
        emoji="✅",
        custom_id="securitybot:verify_button",
    )
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = get_guild_config(interaction.guild_id)
        role_id = config.get("verification_role_id")
        if not role_id:
            await interaction.response.send_message(
                "Verification isn't configured on this server yet.", ephemeral=True
            )
            return

        role = interaction.guild.get_role(role_id)
        if role is None:
            await interaction.response.send_message(
                "The verification role no longer exists — contact an admin.", ephemeral=True
            )
            return

        if role in interaction.user.roles:
            await interaction.response.send_message("You're already verified!", ephemeral=True)
            return

        try:
            await interaction.user.add_roles(role, reason="Passed verification")
        except discord.Forbidden:
            await interaction.response.send_message(
                "I don't have permission to give you that role — contact an admin.", ephemeral=True
            )
            return

        # Remove the "unverified" role too, if one is configured
        unverified_role_id = config.get("unverified_role_id")
        if unverified_role_id:
            unverified_role = interaction.guild.get_role(unverified_role_id)
            if unverified_role and unverified_role in interaction.user.roles:
                try:
                    await interaction.user.remove_roles(unverified_role, reason="Passed verification")
                except discord.Forbidden:
                    pass  # verified role was still granted, so don't block the user on this

        await interaction.response.send_message("✅ You're verified! Welcome.", ephemeral=True)

        embed = discord.Embed(
            title="✅ Member Verified",
            description=f"{interaction.user.mention} completed verification.",
            color=discord.Color.green(),
        )
        await send_log(interaction.client, interaction.guild, embed)


class Verification(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Register the persistent view so the button works after bot restarts
        self.bot.add_view(VerifyView())

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        config = get_guild_config(member.guild.id)
        unverified_role_id = config.get("unverified_role_id")
        if not unverified_role_id:
            return
        role = member.guild.get_role(unverified_role_id)
        if role is None:
            return
        try:
            await member.add_roles(role, reason="New member - pending verification")
        except discord.Forbidden:
            pass

    @app_commands.command(name="set-unverified-role", description="Set the role auto-assigned to new members until they verify.")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_unverified_role(self, interaction: discord.Interaction, role: discord.Role):
        from utils.storage import update_guild_config
        update_guild_config(interaction.guild_id, lambda cfg: cfg.update(unverified_role_id=role.id))
        await interaction.response.send_message(
            f"✅ New members will now automatically receive {role.mention} until they verify.",
            ephemeral=True,
        )

    @app_commands.command(name="setup-verification", description="Post the verification panel in this channel.")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_verification(self, interaction: discord.Interaction):
        config = get_guild_config(interaction.guild_id)
        if not config.get("verification_role_id"):
            await interaction.response.send_message(
                "Set a verification role first with `/set-verification-role`.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="🔒 Server Verification",
            description="Click the button below to verify yourself and gain access to the server.",
            color=discord.Color.blurple(),
        )
        await interaction.channel.send(embed=embed, view=VerifyView())
        await interaction.response.send_message("Verification panel posted.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Verification(bot))
