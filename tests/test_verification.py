import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import discord
from discord.ext import commands

from cogs.verification import (
    Verification,
    VerifyView,
    generate_captcha_code,
    validate_captcha_code,
    handle_verification_success,
)
from utils.database import init_db, update_guild_config


@pytest.fixture
async def temp_db(tmp_path):
    db_file = str(tmp_path / "test_verification.db")
    await init_db(db_file)
    yield db_file


@pytest.fixture
def mock_bot(temp_db):
    bot = MagicMock(spec=commands.Bot)
    bot.user = MagicMock(spec=discord.ClientUser)
    bot.user.id = 11111111
    bot.db_path = temp_db
    bot.add_view = MagicMock()
    return bot


@pytest.fixture
def verification_cog(mock_bot):
    cog = Verification(mock_bot)
    cog.db_path = mock_bot.db_path
    return cog


def test_captcha_code_generation_and_validation():
    code = generate_captcha_code()
    assert len(code) == 5
    assert code.isalnum()

    assert validate_captcha_code("A7X9K", "a7x9k") is True
    assert validate_captcha_code("A7X9K", " A7X9K ") is True
    assert validate_captcha_code("A7X9K", "WRONG") is False


@pytest.mark.asyncio
async def test_verification_success_assigns_roles(temp_db):
    guild = MagicMock(spec=discord.Guild)
    guild.id = 12345
    guild.name = "Verify Guild"

    verify_role = MagicMock(spec=discord.Role)
    verify_role.id = 701
    unverify_role = MagicMock(spec=discord.Role)
    unverify_role.id = 702

    guild.get_role = MagicMock(side_effect=lambda rid: {701: verify_role, 702: unverify_role}.get(rid))

    user = MagicMock(spec=discord.Member)
    user.id = 555
    user.mention = "<@555>"
    user.roles = [unverify_role]
    user.add_roles = AsyncMock()
    user.remove_roles = AsyncMock()

    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild_id = guild.id
    interaction.guild = guild
    interaction.user = user
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()
    interaction.client = MagicMock()

    await update_guild_config(
        guild.id,
        verification_role_id=701,
        unverified_role_id=702,
        db_path=temp_db,
    )

    with patch("cogs.verification.send_log", new_callable=AsyncMock) as mock_send_log:
        await handle_verification_success(interaction, db_path=temp_db)
        user.add_roles.assert_called_once_with(verify_role, reason="Passed verification")
        user.remove_roles.assert_called_once_with(unverify_role, reason="Passed verification")
        interaction.response.send_message.assert_called_once()
        mock_send_log.assert_called_once()
