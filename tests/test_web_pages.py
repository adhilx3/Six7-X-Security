import pytest
import os
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from utils import database as db

@pytest.fixture(autouse=True)
async def setup_test_db(tmp_path, monkeypatch):
    test_db = str(tmp_path / "test_pages_six7.db")
    monkeypatch.setattr(db, "DEFAULT_DB_PATH", test_db)
    await db.init_db(test_db)
    yield

@pytest.fixture
def pages_app():
    from web.routes.pages import pages_router
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test_secret_pages_12345")
    app.include_router(pages_router)

    # Attach mock bot
    mock_bot = MagicMock()
    mock_bot.is_ready.return_value = True
    mock_bot.latency = 0.035
    mock_bot.start_time = 1000.0

    mock_guild = MagicMock()
    mock_guild.id = 123456
    mock_guild.name = "Six7 Test Guild"
    mock_guild.member_count = 42
    mock_guild.icon = None
    mock_channel = MagicMock(id=999, name="general")
    mock_role = MagicMock(id=888, name="Verified Member")
    mock_guild.channels = [mock_channel]
    mock_guild.text_channels = [mock_channel]
    mock_guild.roles = [mock_role]

    mock_bot.guilds = [mock_guild]
    mock_bot.get_guild.return_value = mock_guild
    app.state.bot = mock_bot

    return app

def test_unauthenticated_overview_redirects_to_login(pages_app):
    client = TestClient(pages_app, follow_redirects=False)
    resp = client.get("/")
    assert resp.status_code in (302, 303, 307)
    assert resp.headers["location"] == "/login"

def test_login_page_renders(pages_app):
    client = TestClient(pages_app)
    resp = client.get("/login")
    assert resp.status_code == 200
    assert "Six7 Security" in resp.text
    assert "Password" in resp.text

def test_login_post_valid_password(pages_app, monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD", "correct_pass")
    client = TestClient(pages_app, follow_redirects=False)
    resp = client.post("/login", data={"password": "correct_pass"})
    assert resp.status_code in (302, 303)
    assert resp.headers["location"] == "/"

def test_login_post_invalid_password(pages_app, monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD", "correct_pass")
    client = TestClient(pages_app, follow_redirects=False)
    resp = client.post("/login", data={"password": "wrong_pass"})
    assert resp.status_code in (302, 303)
    assert "/login" in resp.headers["location"]

def test_logout(pages_app):
    client = TestClient(pages_app, follow_redirects=False)
    resp = client.get("/logout")
    assert resp.status_code in (302, 303)
    assert resp.headers["location"] == "/login"

def test_authenticated_overview_renders_guilds(pages_app, monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD", "correct_pass")
    client = TestClient(pages_app)
    # Log in first to establish signed session cookie
    client.post("/login", data={"password": "correct_pass"})

    resp = client.get("/")
    assert resp.status_code == 200
    assert "Six7 Test Guild" in resp.text
    assert "42" in resp.text

def test_guild_dashboard_page(pages_app, monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD", "correct_pass")
    client = TestClient(pages_app)
    client.post("/login", data={"password": "correct_pass"})

    guild_id = 123456
    resp = client.get(f"/guild/{guild_id}")
    assert resp.status_code == 200
    assert "Anti-Nuke" in resp.text
    assert "Anti-Raid" in resp.text
    assert "AutoMod" in resp.text
    assert "Verification" in resp.text
    assert "Warnings" in resp.text
