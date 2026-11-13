import pytest
import os
import aiosqlite
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from utils import database as db

@pytest.fixture(autouse=True)
async def setup_test_db(tmp_path, monkeypatch):
    """Use temporary SQLite database for test isolation."""
    test_db = str(tmp_path / "test_api_six7.db")
    monkeypatch.setattr(db, "DEFAULT_DB_PATH", test_db)
    await db.init_db(test_db)
    yield

@pytest.fixture
def test_app():
    from web.routes.api import api_router
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test_secret_key_12345")
    app.include_router(api_router)

    # Attach mock bot to app.state.bot
    mock_bot = MagicMock()
    mock_bot.is_ready.return_value = True
    mock_bot.latency = 0.042
    mock_bot.guilds = [MagicMock(id=123456)]
    mock_bot.start_time = 1000.0
    app.state.bot = mock_bot
    return app

def test_api_health(test_app):
    client = TestClient(test_app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["latency_ms"] == 42.0
    assert data["guilds_count"] == 1

def test_api_unauthenticated_rejected(test_app):
    client = TestClient(test_app)
    # Posting to any guild endpoint without a session cookie should return 401
    resp = client.post("/api/guild/123456/antinuke", json={"punishment": "ban"})
    assert resp.status_code == 401

def test_api_forbidden_guild_access(test_app):
    client = TestClient(test_app)
    with patch("web.auth.get_current_user") as mock_user:
        mock_user.return_value = {
            "username": "mod",
            "is_master_admin": False,
            "guilds": [999999]
        }
        resp = client.post("/api/guild/123456/antinuke", json={"punishment": "ban"})
        assert resp.status_code == 403

def test_api_input_validation(test_app):
    client = TestClient(test_app)
    with patch("web.auth.get_current_user") as mock_user:
        mock_user.return_value = {"username": "admin", "is_master_admin": True}
        # Negative limit
        resp = client.post("/api/guild/123456/antinuke", json={"max_channel_actions": -5})
        assert resp.status_code == 400
        # Invalid punishment
        resp = client.post("/api/guild/123456/antinuke", json={"punishment": "destroy_all"})
        assert resp.status_code == 400

@pytest.mark.asyncio
async def test_api_antinuke_and_whitelist(test_app):
    client = TestClient(test_app)
    guild_id = 123456
    with patch("web.auth.get_current_user") as mock_user:
        mock_user.return_value = {"username": "admin", "is_master_admin": True}

        # 1. Update Anti-Nuke settings
        resp = client.post(
            f"/api/guild/{guild_id}/antinuke",
            json={"max_channel_actions": 5, "punishment": "ban", "enabled": 1}
        )
        assert resp.status_code == 200
        cfg = await db.get_antinuke_config(guild_id)
        assert cfg["max_channel_actions"] == 5
        assert cfg["punishment"] == "ban"
        assert cfg["enabled"] == 1

        # 2. Add to Whitelist
        resp = client.post(
            f"/api/guild/{guild_id}/whitelist",
            json={"action": "add", "target_id": 998877, "reason": "trusted"}
        )
        assert resp.status_code == 200
        assert await db.is_antinuke_whitelisted(guild_id, 998877) is True

        # 3. Remove from Whitelist
        resp = client.post(
            f"/api/guild/{guild_id}/whitelist",
            json={"action": "remove", "target_id": 998877}
        )
        assert resp.status_code == 200
        assert await db.is_antinuke_whitelisted(guild_id, 998877) is False

@pytest.mark.asyncio
async def test_api_antiraid_and_lockdown(test_app):
    client = TestClient(test_app)
    guild_id = 123456
    with patch("web.auth.get_current_user") as mock_user:
        mock_user.return_value = {"username": "admin", "is_master_admin": True}

        # 1. Update Anti-Raid settings
        resp = client.post(
            f"/api/guild/{guild_id}/antiraid",
            json={"join_threshold": 8, "join_time_window": 15, "min_account_age_days": 7, "action_on_raid": "kick"}
        )
        assert resp.status_code == 200
        cfg = await db.get_antiraid_config(guild_id)
        assert cfg["join_threshold"] == 8
        assert cfg["join_time_window"] == 15
        assert cfg["min_account_age_days"] == 7
        assert cfg["action_on_raid"] == "kick"

        # 2. Toggle Lockdown
        mock_cog = MagicMock()
        mock_cog.enable_lockdown = AsyncMock(return_value=[111, 222])
        mock_cog.disable_lockdown = AsyncMock(return_value=[111, 222])
        test_app.state.bot.get_cog.return_value = mock_cog
        mock_guild = MagicMock()
        test_app.state.bot.get_guild.return_value = mock_guild

        resp = client.post(f"/api/guild/{guild_id}/lockdown", json={"state": True})
        assert resp.status_code == 200
        assert resp.json()["lockdown_active"] is True
        mock_cog.enable_lockdown.assert_awaited_once()

@pytest.mark.asyncio
async def test_api_automod_and_verification(test_app):
    client = TestClient(test_app)
    guild_id = 123456
    with patch("web.auth.get_current_user") as mock_user:
        mock_user.return_value = {"username": "admin", "is_master_admin": True}

        # 1. Update AutoMod
        resp = client.post(
            f"/api/guild/{guild_id}/automod",
            json={
                "banned_words": ["badword1", "badword2"],
                "block_scams": 1,
                "block_attachments": 1,
                "spam_message_count": 6
            }
        )
        assert resp.status_code == 200
        cfg = await db.get_automod_config(guild_id)
        assert "badword1" in cfg["banned_words"]
        assert cfg["block_scams"] == 1
        assert cfg["block_attachments"] == 1
        assert cfg["spam_message_count"] == 6

        # 2. Update Verification
        resp = client.post(
            f"/api/guild/{guild_id}/verification",
            json={"verification_type": "captcha", "verification_role_id": 554433}
        )
        assert resp.status_code == 200
        g_cfg = await db.get_guild_config(guild_id)
        assert g_cfg["verification_type"] == "captcha"
        assert g_cfg["verification_role_id"] == 554433

@pytest.mark.asyncio
async def test_api_warnings_delete(test_app):
    client = TestClient(test_app)
    guild_id = 123456
    with patch("web.auth.get_current_user") as mock_user:
        mock_user.return_value = {"username": "admin", "is_master_admin": True}

        # Add warning first
        warn_id = await db.add_warning(guild_id, 111, 222, "Test violation")
        warnings = await db.get_warnings(guild_id, 111)
        assert len(warnings) == 1

        # Delete warning via API
        resp = client.post(
            f"/api/guild/{guild_id}/warnings/delete",
            json={"warning_id": warn_id}
        )
        assert resp.status_code == 200
        warnings_after = await db.get_warnings(guild_id, 111)
        assert len(warnings_after) == 0
