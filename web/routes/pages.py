import os
import time
import secrets
from typing import Optional
from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from web.auth import (
    verify_password,
    get_current_user,
    get_discord_oauth_url,
    exchange_discord_code
)
from utils import database as db

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

templates = Jinja2Templates(directory=TEMPLATES_DIR)
pages_router = APIRouter()


def format_uptime(start_time: Optional[float]) -> str:
    if not start_time:
        return "0s"
    seconds = int(time.time() - start_time)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}h {minutes}m"
    if minutes > 0:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


# ---------- Overview Page ----------

@pages_router.get("/", response_class=HTMLResponse)
async def overview_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    bot = getattr(request.app.state, "bot", None)
    all_guilds = getattr(bot, "guilds", []) if bot else []

    if user.get("is_master_admin"):
        accessible_guilds = all_guilds
    else:
        user_guild_ids = set(user.get("guilds", []))
        accessible_guilds = [g for g in all_guilds if g.id in user_guild_ids]

    latency_ms = round(bot.latency * 1000, 2) if bot and hasattr(bot, "latency") else 0.0
    start_time = getattr(bot, "start_time", None)
    stats = {
        "guilds_count": len(all_guilds),
        "latency_ms": latency_ms,
        "uptime_str": format_uptime(start_time)
    }

    return templates.TemplateResponse(
        request=request,
        name="overview.html",
        context={
            "user": user,
            "guilds": accessible_guilds,
            "stats": stats
        }
    )


# ---------- Login & Logout Routes ----------

@pages_router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: Optional[str] = None):
    user = get_current_user(request)
    if user:
        return RedirectResponse(url="/", status_code=302)

    discord_oauth_enabled = bool(
        os.getenv("DISCORD_CLIENT_ID") and os.getenv("DISCORD_CLIENT_SECRET")
    )

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "user": None,
            "error": error,
            "discord_oauth_enabled": discord_oauth_enabled
        }
    )


@pages_router.post("/login")
async def login_post(request: Request, password: str = Form(...)):
    if verify_password(password):
        request.session["user"] = {
            "auth_type": "password",
            "username": "Master Admin",
            "is_master_admin": True,
            "guilds": []
        }
        return RedirectResponse(url="/", status_code=303)

    return RedirectResponse(url="/login?error=invalid_password", status_code=303)


@pages_router.get("/logout")
async def logout(request: Request):
    if hasattr(request, "session"):
        request.session.clear()
    return RedirectResponse(url="/login", status_code=302)


# ---------- Discord OAuth2 Routes ----------

@pages_router.get("/auth/discord")
async def discord_oauth_start(request: Request):
    client_id = os.getenv("DISCORD_CLIENT_ID")
    client_secret = os.getenv("DISCORD_CLIENT_SECRET")
    if not client_id or not client_secret:
        return RedirectResponse(url="/login?error=oauth_not_configured", status_code=302)

    redirect_uri = os.getenv("DISCORD_REDIRECT_URI")
    if not redirect_uri:
        redirect_uri = str(request.url_for("discord_callback"))

    state = secrets.token_urlsafe(16)
    request.session["oauth_state"] = state

    auth_url = get_discord_oauth_url(
        redirect_uri=redirect_uri,
        client_id=client_id,
        state=state
    )
    return RedirectResponse(url=auth_url, status_code=302)


@pages_router.get("/auth/discord/callback")
async def discord_callback(request: Request, code: Optional[str] = None, state: Optional[str] = None):
    expected_state = request.session.get("oauth_state")
    if not state or not expected_state or state != expected_state:
        return RedirectResponse(url="/login?error=oauth_failed", status_code=302)

    if not code:
        return RedirectResponse(url="/login?error=oauth_failed", status_code=302)

    client_id = os.getenv("DISCORD_CLIENT_ID", "")
    client_secret = os.getenv("DISCORD_CLIENT_SECRET", "")
    redirect_uri = os.getenv("DISCORD_REDIRECT_URI")
    if not redirect_uri:
        redirect_uri = str(request.url_for("discord_callback"))

    try:
        user_profile = await exchange_discord_code(
            code=code,
            redirect_uri=redirect_uri,
            client_id=client_id,
            client_secret=client_secret
        )
        request.session["user"] = user_profile
        return RedirectResponse(url="/", status_code=302)
    except Exception:
        return RedirectResponse(url="/login?error=oauth_failed", status_code=302)


# ---------- Guild Management Dashboard Page ----------

@pages_router.get("/guild/{guild_id}", response_class=HTMLResponse)
async def guild_dashboard_page(guild_id: int, request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    if not user.get("is_master_admin"):
        user_guilds = [int(g) for g in user.get("guilds", [])]
        if guild_id not in user_guilds:
            raise HTTPException(
                status_code=403,
                detail="Forbidden: You do not have administrator permissions in this server."
            )

    bot = getattr(request.app.state, "bot", None)
    guild = bot.get_guild(guild_id) if bot and hasattr(bot, "get_guild") else None

    if not guild:
        # Fallback dummy object if bot is starting or test mode
        class DummyGuild:
            id = guild_id
            name = f"Guild {guild_id}"
            member_count = 0
            icon = None
            channels = []
            text_channels = []
            roles = []
        guild = DummyGuild()

    guild_cfg = await db.get_guild_config(guild_id)
    antinuke_cfg = await db.get_antinuke_config(guild_id)
    antiraid_cfg = await db.get_antiraid_config(guild_id)
    automod_cfg = await db.get_automod_config(guild_id)
    whitelist = await db.get_antinuke_whitelist(guild_id)
    warnings = await db.get_warnings(guild_id)

    return templates.TemplateResponse(
        request=request,
        name="guild.html",
        context={
            "user": user,
            "guild": guild,
            "guild_cfg": guild_cfg,
            "antinuke_cfg": antinuke_cfg,
            "antiraid_cfg": antiraid_cfg,
            "automod_cfg": automod_cfg,
            "whitelist": whitelist,
            "warnings": warnings
        }
    )
