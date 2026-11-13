import datetime
import random
import string

import discord
from discord import app_commands
from discord.ext import commands

from utils.database import get_guild_config, update_guild_config
from cogs.logging_cog import send_log

CAPTCHA_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_captcha_code(length: int = 5) -> str:
    return "".join(random.choices(CAPTCHA_CHARS, k=length))


def validate_captcha_code(expected: str, given: str) -> bool:
    return expected.strip().upper() == given.strip().upper()


async def handle_verification_success(interaction: discord.Interaction, db_path: str = None):
    config = await get_guild_config(interaction.guild_id, db_path=db_path)
    role_id = config.get("verification_role_id")
    if not role_id:
        await interaction.response.send_message(
            "❌ Verification isn't configured on this server yet.", ephemeral=True
        )
        return

    role = interaction.guild.get_role(role_id) if hasattr(interaction.guild, "get_role") else None
    if role is None:
        await interaction.response.send_message(
            "❌ The verification role no longer exists — contact an admin.", ephemeral=True
        )
        return

    if role in getattr(interaction.user, "roles", []):
        await interaction.response.send_message("You're already verified!", ephemeral=True)
        return

    try:
        await interaction.user.add_roles(role, reason="Passed verification")
    except (discord.Forbidden, discord.HTTPException):
        await interaction.response.send_message(
            "❌ I don't have permission to give you that role — contact an admin.", ephemeral=True
        )
        return

    # Remove unverified role if configured
    unverified_role_id = config.get("unverified_role_id")
    if unverified_role_id:
        unverified_role = interaction.guild.get_role(unverified_role_id) if hasattr(interaction.guild, "get_role") else None
        if unverified_role and unverified_role in getattr(interaction.user, "roles", []):
            try:
                await interaction.user.remove_roles(unverified_role, reason="Passed verification")
            except (discord.Forbidden, discord.HTTPException):
                pass

    await interaction.response.send_message("✅ You're verified! Welcome.", ephemeral=True)

    embed = discord.Embed(
        title="✅ Member Verified",
        description=f"{interaction.user.mention} completed verification.",
        color=discord.Color.green(),
        timestamp=datetime.datetime.now(datetime.timezone.utc),
    )
    await send_log(getattr(interaction, "client", None), interaction.guild, embed)


class CaptchaModal(discord.ui.Modal, title="Verification Challenge"):
    def __init__(self, expected_code: str, db_path: str = None):
        super().__init__()
        self.expected_code = expected_code
        self.db_path = db_path
        self.code_input = discord.ui.TextInput(
            label=f"Enter code: {expected_code}",
            placeholder="Type the 5-character code here...",
            min_length=4,
            max_length=10,
        )
        self.add_item(self.code_input)

    async def on_submit(self, interaction: discord.Interaction):
        if validate_captcha_code(self.expected_code, self.code_input.value):
            await handle_verification_success(interaction, db_path=self.db_path)
        else:
            await interaction.response.send_message(
                "❌ Incorrect verification code. Click Verify to try again.",
                ephemeral=True,
            )


class VerifyView(discord.ui.View):
    def __init__(self, db_path: str = None):
        super().__init__(timeout=None)
        self.db_path = db_path

    @discord.ui.button(
        label="Verify",
        style=discord.ButtonStyle.success,
        emoji="✅",
        custom_id="securitybot:verify_button",
    )
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = await get_guild_config(interaction.guild_id, db_path=self.db_path)
        mode = config.get("verification_type", "button")

        if mode == "captcha":
            code = generate_captcha_code()
            await interaction.response.send_modal(CaptchaModal(expected_code=code, db_path=self.db_path))
        else:
            await handle_verification_success(interaction, db_path=self.db_path)


class Verification(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_path = getattr(bot, "db_path", None)
        self.bot.add_view(VerifyView(db_path=self.db_path))

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot or member.guild is None:
            return

        config = await get_guild_config(member.guild.id, db_path=self.db_path)
        unverified_role_id = config.get("unverified_role_id")
        if not unverified_role_id:
            return
        role = member.guild.get_role(unverified_role_id)
        if role is None:
            return
        try:
            await member.add_roles(role, reason="New member - pending verification")
        except (discord.Forbidden, discord.HTTPException):
            pass

    @app_commands.command(name="set-verification-mode", description="Choose between button click or captcha challenge.")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Button Click (Standard)", value="button"),
        app_commands.Choice(name="Captcha Challenge (Anti-Bot)", value="captcha"),
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def set_verification_mode(self, interaction: discord.Interaction, mode: app_commands.Choice[str]):
        await update_guild_config(interaction.guild_id, verification_type=mode.value, db_path=self.db_path)
        await interaction.response.send_message(
            f"✅ Verification mode set to **{mode.name}**.", ephemeral=True
        )

    @app_commands.command(name="set-verification-role", description="Set the role given to verified members.")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_verification_role(self, interaction: discord.Interaction, role: discord.Role):
        await update_guild_config(interaction.guild_id, verification_role_id=role.id, db_path=self.db_path)
        await interaction.response.send_message(f"✅ Verification role set to {role.mention}.", ephemeral=True)

    @app_commands.command(name="set-unverified-role", description="Set the role auto-assigned to new members until they verify.")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_unverified_role(self, interaction: discord.Interaction, role: discord.Role):
        await update_guild_config(interaction.guild_id, unverified_role_id=role.id, db_path=self.db_path)
        await interaction.response.send_message(
            f"✅ New members will now automatically receive {role.mention} until they verify.",
            ephemeral=True,
        )

    @app_commands.command(name="setup-verification", description="Post the verification panel in this channel.")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_verification(self, interaction: discord.Interaction):
        config = await get_guild_config(interaction.guild_id, db_path=self.db_path)
        if not config.get("verification_role_id"):
            await interaction.response.send_message(
                "❌ Set a verification role first with `/set-verification-role`.", ephemeral=True
            )
            return

        mode_name = "Captcha Code" if config.get("verification_type") == "captcha" else "Button"
        embed = discord.Embed(
            title="🔒 Server Verification",
            description=f"Click the button below to complete verification ({mode_name}) and gain access to the server.",
            color=discord.Color.blurple(),
        )
        await interaction.channel.send(embed=embed, view=VerifyView(db_path=self.db_path))
        await interaction.response.send_message("✅ Verification panel posted.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Verification(bot))
