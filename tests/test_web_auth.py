import pytest
import os
from unittest.mock import AsyncMock, patch, MagicMock
from starlette.requests import Request
from fastapi import HTTPException

# Test Task 1: Web Auth
def test_password_verification(monkeypatch):
    monkeypatch.setenv("DASHBOARD_PASSWORD", "SuperSecretPass123!")
    from web.auth import verify_password
    assert verify_password("SuperSecretPass123!") is True
    assert verify_password("WrongPassword") is False
    assert verify_password("") is False

def test_get_current_user_from_session():
    from web.auth import get_current_user
    mock_request = MagicMock()
    mock_request.session = {"user": {"username": "admin", "is_master_admin": True}}
    user = get_current_user(mock_request)
    assert user is not None
    assert user["username"] == "admin"
    assert user["is_master_admin"] is True

    # Empty session
    mock_request.session = {}
    assert get_current_user(mock_request) is None

def test_require_admin_authorization():
    from web.auth import require_admin

    # 1. Unauthenticated -> 401
    mock_request = MagicMock()
    mock_request.session = {}
    with pytest.raises(HTTPException) as exc_info:
        require_admin(123456789, mock_request)
    assert exc_info.value.status_code == 401

    # 2. Master admin -> allowed for any guild
    mock_request.session = {"user": {"username": "admin", "is_master_admin": True}}
    user = require_admin(123456789, mock_request)
    assert user["is_master_admin"] is True

    # 3. Discord OAuth user with permission
    mock_request.session = {
        "user": {
            "username": "discord_mod",
            "is_master_admin": False,
            "guilds": [123456789, 987654321]
        }
    }
    user = require_admin(123456789, mock_request)
    assert user["username"] == "discord_mod"

    # 4. Discord OAuth user without permission -> 403
    with pytest.raises(HTTPException) as exc_info:
        require_admin(555555555, mock_request)
    assert exc_info.value.status_code == 403

def test_get_discord_oauth_url():
    from web.auth import get_discord_oauth_url
    url = get_discord_oauth_url(
        redirect_uri="http://localhost:8080/auth/discord/callback",
        client_id="123456",
        state="xyzstate"
    )
    assert "https://discord.com/api/oauth2/authorize" in url
    assert "client_id=123456" in url
    assert "identify" in url
    assert "guilds" in url
    assert "state=xyzstate" in url

@pytest.mark.asyncio
async def test_exchange_discord_code_success():
    from web.auth import exchange_discord_code

    mock_token_resp = MagicMock()
    mock_token_resp.status_code = 200
    mock_token_resp.json.return_value = {"access_token": "mock_token_abc"}

    mock_user_resp = MagicMock()
    mock_user_resp.status_code = 200
    mock_user_resp.json.return_value = {"id": "111222", "username": "alice", "avatar": "avatar_hash"}

    mock_guilds_resp = MagicMock()
    mock_guilds_resp.status_code = 200
    # Guild 1: has admin permission (0x8), Guild 2: owner, Guild 3: regular member (0x0)
    mock_guilds_resp.json.return_value = [
        {"id": "100", "name": "Admin Guild", "permissions": str(0x8), "owner": False},
        {"id": "200", "name": "Owner Guild", "permissions": "0", "owner": True},
        {"id": "300", "name": "Member Guild", "permissions": "0", "owner": False},
    ]

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_token_resp):
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = [mock_user_resp, mock_guilds_resp]

            result = await exchange_discord_code("test_code", "http://localhost/callback", "id", "secret")
            assert result["user_id"] == "111222"
            assert result["username"] == "alice"
            assert 100 in result["guilds"]
            assert 200 in result["guilds"]
            assert 300 not in result["guilds"]
