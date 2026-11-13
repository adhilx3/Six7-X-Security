import time
from typing import Dict, Any, Optional
from fastapi import APIRouter, Request, HTTPException, Body
from web.auth import require_admin
from utils import database as db

api_router = APIRouter(prefix="/api")


@api_router.get("/health")
async def health_check(request: Request):
    """Health check endpoint reporting bot metrics and operational status."""
    bot = getattr(request.app.state, "bot", None)
    latency_ms = round(bot.latency * 1000, 2) if bot and hasattr(bot, "latency") else 0.0
    guilds_count = len(bot.guilds) if bot and hasattr(bot, "guilds") else 0
    start_time = getattr(bot, "start_time", None)
    uptime_seconds = round(time.time() - start_time, 2) if start_time else 0.0

    return {
        "status": "ok",
        "bot_ready": bool(bot and getattr(bot, "is_ready", lambda: False)()),
        "latency_ms": latency_ms,
        "guilds_count": guilds_count,
        "uptime_seconds": uptime_seconds
    }


# ---------- Anti-Nuke Endpoints ----------

@api_router.post("/guild/{guild_id}/antinuke")
async def update_antinuke(
    guild_id: int,
    request: Request,
    payload: Dict[str, Any] = Body(...)
):
    require_admin(guild_id, request)

    valid_punishments = {"strip_roles", "ban", "kick"}
    punishment = payload.get("punishment")
    if punishment and punishment not in valid_punishments:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid punishment. Must be one of: {', '.join(valid_punishments)}"
        )

    int_fields = [
        "max_channel_actions",
        "max_role_actions",
        "max_member_actions",
        "max_webhook_actions",
        "action_window_seconds"
    ]
    updates = {}
    for field in int_fields:
        if field in payload:
            val = payload[field]
            if not isinstance(val, int) or val < 1:
                raise HTTPException(status_code=400, detail=f"{field} must be a positive integer.")
            updates[field] = val

    if "enabled" in payload:
        updates["enabled"] = 1 if payload["enabled"] else 0
    if punishment:
        updates["punishment"] = punishment

    if updates:
        await db.update_antinuke_config(guild_id, **updates)

    cfg = await db.get_antinuke_config(guild_id)
    return {"status": "success", "config": cfg}


@api_router.post("/guild/{guild_id}/whitelist")
async def modify_whitelist(
    guild_id: int,
    request: Request,
    payload: Dict[str, Any] = Body(...)
):
    user = require_admin(guild_id, request)
    action = payload.get("action")
    target_id = payload.get("target_id")

    if not action or action not in {"add", "remove"}:
        raise HTTPException(status_code=400, detail="Action must be 'add' or 'remove'.")
    if not target_id or not isinstance(target_id, int):
        raise HTTPException(status_code=400, detail="Valid integer target_id is required.")

    if action == "add":
        reason = str(payload.get("reason", "Added via Web Dashboard"))
        added_by = int(user.get("user_id", 0)) if user.get("user_id") else 0
        await db.add_antinuke_whitelist(guild_id, target_id, reason=reason, added_by=added_by)
    else:
        await db.remove_antinuke_whitelist(guild_id, target_id)

    whitelist = await db.get_antinuke_whitelist(guild_id)
    return {"status": "success", "whitelist": whitelist}


# ---------- Anti-Raid & Lockdown Endpoints ----------

@api_router.post("/guild/{guild_id}/antiraid")
async def update_antiraid(
    guild_id: int,
    request: Request,
    payload: Dict[str, Any] = Body(...)
):
    require_admin(guild_id, request)

    valid_actions = {"kick", "ban", "timeout"}
    action = payload.get("action_on_raid")
    if action and action not in valid_actions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid action_on_raid. Must be one of: {', '.join(valid_actions)}"
        )

    int_fields = ["join_threshold", "join_time_window", "min_account_age_days"]
    updates = {}
    for field in int_fields:
        if field in payload:
            val = payload[field]
            if not isinstance(val, int) or val < 0:
                raise HTTPException(status_code=400, detail=f"{field} must be a non-negative integer.")
            updates[field] = val

    if "enabled" in payload:
        updates["enabled"] = 1 if payload["enabled"] else 0
    if "anti_bot_enabled" in payload:
        updates["anti_bot_enabled"] = 1 if payload["anti_bot_enabled"] else 0
    if action:
        updates["action_on_raid"] = action

    if updates:
        await db.update_antiraid_config(guild_id, **updates)

    cfg = await db.get_antiraid_config(guild_id)
    return {"status": "success", "config": cfg}


@api_router.post("/guild/{guild_id}/lockdown")
async def toggle_lockdown(
    guild_id: int,
    request: Request,
    payload: Dict[str, Any] = Body(...)
):
    require_admin(guild_id, request)
    state = bool(payload.get("state", False))

    bot = getattr(request.app.state, "bot", None)
    if bot:
        cog = bot.get_cog("AntiRaidCog")
        guild = bot.get_guild(guild_id)
        if cog and guild:
            if state:
                await cog.enable_lockdown(guild)
            else:
                await cog.disable_lockdown(guild)

    await db.update_antiraid_config(guild_id, lockdown_active=1 if state else 0)
    return {"status": "success", "lockdown_active": state}


# ---------- AutoMod Endpoints ----------

@api_router.post("/guild/{guild_id}/automod")
async def update_automod(
    guild_id: int,
    request: Request,
    payload: Dict[str, Any] = Body(...)
):
    require_admin(guild_id, request)

    updates = {}
    if "banned_words" in payload:
        words = payload["banned_words"]
        if not isinstance(words, list):
            raise HTTPException(status_code=400, detail="banned_words must be a list of strings.")
        updates["banned_words"] = [str(w).strip().lower() for w in words if str(w).strip()]

    int_fields = ["max_mentions", "max_caps_percent", "spam_message_count", "spam_time_window"]
    for field in int_fields:
        if field in payload:
            val = payload[field]
            if not isinstance(val, int) or val < 1:
                raise HTTPException(status_code=400, detail=f"{field} must be a positive integer.")
            updates[field] = val

    bool_fields = ["enabled", "block_invites", "block_scams", "block_attachments", "block_duplicates"]
    for field in bool_fields:
        if field in payload:
            updates[field] = 1 if payload[field] else 0

    if updates:
        await db.update_automod_config(guild_id, **updates)

    cfg = await db.get_automod_config(guild_id)
    return {"status": "success", "config": cfg}


# ---------- Verification Endpoints ----------

@api_router.post("/guild/{guild_id}/verification")
async def update_verification(
    guild_id: int,
    request: Request,
    payload: Dict[str, Any] = Body(...)
):
    require_admin(guild_id, request)

    updates = {}
    if "verification_type" in payload:
        v_type = payload["verification_type"]
        if v_type not in {"button", "captcha"}:
            raise HTTPException(status_code=400, detail="verification_type must be 'button' or 'captcha'.")
        updates["verification_type"] = v_type

    id_fields = ["verification_role_id", "verification_channel_id", "unverified_role_id", "log_channel_id"]
    for field in id_fields:
        if field in payload:
            val = payload[field]
            if val is not None and not isinstance(val, int):
                raise HTTPException(status_code=400, detail=f"{field} must be an integer ID or null.")
            updates[field] = val

    if updates:
        await db.update_guild_config(guild_id, **updates)

    cfg = await db.get_guild_config(guild_id)
    return {"status": "success", "config": cfg}


# ---------- Warnings Endpoints ----------

@api_router.post("/guild/{guild_id}/warnings/delete")
async def delete_warning_endpoint(
    guild_id: int,
    request: Request,
    payload: Dict[str, Any] = Body(...)
):
    require_admin(guild_id, request)

    warning_id = payload.get("warning_id")
    if not warning_id or not isinstance(warning_id, int):
        raise HTTPException(status_code=400, detail="warning_id must be a valid integer.")

    await db.delete_warning(warning_id)
    return {"status": "success", "deleted_warning_id": warning_id}
