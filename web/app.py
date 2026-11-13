import os
import secrets
from typing import Optional
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from web.routes.pages import pages_router
from web.routes.api import api_router


def create_app(bot: Optional[object] = None) -> FastAPI:
    """FastAPI application factory for the Six7 Security Web Dashboard."""
    app = FastAPI(
        title="Six7 Security Web Dashboard",
        docs_url=None,
        redoc_url=None
    )

    # Secret key fallback for signed session cookies
    secret_key = os.getenv("SESSION_SECRET")
    if not secret_key:
        secret_key = secrets.token_hex(32)

    app.add_middleware(
        SessionMiddleware,
        secret_key=secret_key,
        max_age=86400 * 7,  # 7 days
        same_site="lax"
    )

    # Static files mounting
    base_dir = os.path.dirname(__file__)
    static_dir = os.path.join(base_dir, "static")
    os.makedirs(static_dir, exist_ok=True)
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    # Attach bot instance to state
    app.state.bot = bot

    # Mount routers
    app.include_router(pages_router)
    app.include_router(api_router)

    return app
