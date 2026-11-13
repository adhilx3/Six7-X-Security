import pytest
import os
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi.testclient import TestClient

# Test Task 4: App factory & Bot lifecycle integration
def test_create_app_factory():
    from web.app import create_app
    mock_bot = MagicMock()
    app = create_app(bot=mock_bot)

    assert app.state.bot == mock_bot
    client = TestClient(app)

    # Healthcheck should be mounted and functional
    mock_bot.is_ready.return_value = True
    mock_bot.latency = 0.025
    mock_bot.guilds = []
    mock_bot.start_time = 100.0

    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # Static files should be mounted
    resp_static = client.get("/static/css/dashboard.css")
    assert resp_static.status_code == 200

@pytest.mark.asyncio
async def test_bot_setup_hook_spawns_web_server(monkeypatch):
    import bot
    monkeypatch.setenv("PORT", "9999")

    test_bot = bot.Six7Bot()
    # Mock bot commands / gateway so we don't start actual Discord network connection
    test_bot.tree.sync = AsyncMock()
    with patch("bot.init_db", new_callable=AsyncMock):
        with patch("bot.migrate_from_json", new_callable=AsyncMock):
            with patch("uvicorn.Server.serve", new_callable=AsyncMock):
                await test_bot.setup_hook()

                assert hasattr(test_bot, "web_server")
                assert hasattr(test_bot, "web_task")
                assert not test_bot.web_task.done()

                # Test graceful shutdown
                await test_bot.close()
                assert test_bot.web_server.should_exit is True
                test_bot.web_task.cancel()
