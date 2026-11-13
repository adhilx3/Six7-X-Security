import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from utils import database as db

@pytest.fixture(autouse=True)
async def setup_test_db(tmp_path, monkeypatch):
    test_db = str(tmp_path / "test_fixes_db.db")
    monkeypatch.setattr(db, "DEFAULT_DB_PATH", test_db)
    await db.init_db(test_db)
    yield

@pytest.fixture
def test_app():
    from web.routes.api import api_router
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test_secret_fixes")
    app.include_router(api_router)

    mock_bot = MagicMock()
    mock_bot.is_ready.return_value = True
    mock_bot.latency = 0.04
    mock_bot.guilds = []
    mock_bot.start_time = 100.0
    app.state.bot = mock_bot
    return app

@pytest.mark.asyncio
async def test_warning_deletion_scoped_to_guild(test_app):
    """Verify that deleting a warning is scoped to the requesting guild (prevents cross-guild IDOR)."""
    client = TestClient(test_app)
    guild_a = 111111
    guild_b = 222222

    # Warning belongs to Guild A
    warn_id = await db.add_warning(guild_a, 999, 888, "Guild A infraction")

    with patch("web.auth.get_current_user") as mock_user:
        mock_user.return_value = {"username": "admin", "is_master_admin": True}

        # Guild B tries to delete Guild A's warning
        resp = client.post(
            f"/api/guild/{guild_b}/warnings/delete",
            json={"warning_id": warn_id}
        )
        assert resp.status_code == 404 or (resp.status_code == 200 and resp.json().get("deleted") is False)

        # Warning must still exist in Guild A!
        remaining = await db.get_warnings(guild_a)
        assert len(remaining) == 1
        assert remaining[0]["id"] == warn_id

@pytest.mark.asyncio
async def test_lockdown_uses_correct_cog_name(test_app):
    """Verify that toggle_lockdown calls bot.get_cog('AntiRaid') and NOT 'AntiRaidCog'."""
    client = TestClient(test_app)
    guild_id = 123456

    mock_cog = MagicMock()
    mock_cog.enable_lockdown = AsyncMock(return_value=[])

    def mock_get_cog(name):
        if name == "AntiRaid":
            return mock_cog
        return None

    test_app.state.bot.get_cog.side_effect = mock_get_cog
    test_app.state.bot.get_guild.return_value = MagicMock()

    with patch("web.auth.get_current_user") as mock_user:
        mock_user.return_value = {"username": "admin", "is_master_admin": True}
        resp = client.post(f"/api/guild/{guild_id}/lockdown", json={"state": True})
        assert resp.status_code == 200
        mock_cog.enable_lockdown.assert_awaited_once()

def test_no_default_password_when_env_unset(monkeypatch):
    """Verify that if DASHBOARD_PASSWORD is not set or empty, 'admin123' is rejected."""
    monkeypatch.delenv("DASHBOARD_PASSWORD", raising=False)
    from web.auth import verify_password
    assert verify_password("admin123") is False
    assert verify_password("") is False

def test_antiraid_zero_threshold_rejected(test_app):
    """Verify join_threshold < 2 is rejected with 400 Bad Request."""
    client = TestClient(test_app)
    with patch("web.auth.get_current_user") as mock_user:
        mock_user.return_value = {"username": "admin", "is_master_admin": True}
        resp = client.post(
            "/api/guild/123456/antiraid",
            json={"join_threshold": 0, "join_time_window": 10}
        )
        assert resp.status_code == 400

        resp2 = client.post(
            "/api/guild/123456/antiraid",
            json={"join_threshold": 5, "join_time_window": 0}
        )
        assert resp2.status_code == 400

@pytest.mark.asyncio
async def test_string_snowflake_parsed_cleanly(test_app):
    """Verify 18-19 digit string snowflakes are accepted and correctly stored as integers."""
    client = TestClient(test_app)
    guild_id = 123456
    snowflake_str = "1194285160822607902"

    with patch("web.auth.get_current_user") as mock_user:
        mock_user.return_value = {"username": "admin", "is_master_admin": True}

        # Whitelist string target_id
        resp = client.post(
            f"/api/guild/{guild_id}/whitelist",
            json={"action": "add", "target_id": snowflake_str, "reason": "trusted"}
        )
        assert resp.status_code == 200
        assert await db.is_antinuke_whitelisted(guild_id, int(snowflake_str)) is True

        # Verification string role_id
        resp2 = client.post(
            f"/api/guild/{guild_id}/verification",
            json={"verification_type": "button", "verification_role_id": snowflake_str}
        )
        assert resp2.status_code == 200
        cfg = await db.get_guild_config(guild_id)
        assert cfg["verification_role_id"] == int(snowflake_str)

