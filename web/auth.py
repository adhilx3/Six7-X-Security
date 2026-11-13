import os
import secrets
import urllib.parse
from typing import Optional, Dict, Any, List
import httpx
from starlette.requests import Request
from fastapi import HTTPException

DISCORD_API_ENDPOINT = "https://discord.com/api"
ADMINISTRATOR_PERMISSION = 0x8


def verify_password(password: str) -> bool:
    """Validate dashboard master password against environment variable using constant-time comparison."""
    expected = os.getenv("DASHBOARD_PASSWORD")
    if not expected or not password:
        return False
    return secrets.compare_digest(password.encode("utf-8"), expected.encode("utf-8"))


def get_current_user(request: Request) -> Optional[Dict[str, Any]]:
    """Retrieve logged-in user profile from signed session cookie."""
    if not hasattr(request, "session"):
        return None
    return request.session.get("user")


def require_admin(guild_id: int, request: Request) -> Dict[str, Any]:
    """Dependency that ensures user is authenticated and authorized to manage the specified guild."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if user.get("is_master_admin"):
        return user

    guilds = [int(g) for g in user.get("guilds", [])]
    if int(guild_id) not in guilds:
        raise HTTPException(
            status_code=403,
            detail="Forbidden: You do not have administrator permissions in this server."
        )

    return user


def get_discord_oauth_url(redirect_uri: str, client_id: str, state: str) -> str:
    """Generate Discord OAuth2 authorization URL with identify and guilds scopes."""
    params = urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "identify guilds",
        "state": state
    })
    return f"{DISCORD_API_ENDPOINT}/oauth2/authorize?{params}"


async def exchange_discord_code(
    code: str,
    redirect_uri: str,
    client_id: str,
    client_secret: str
) -> Dict[str, Any]:
    """Exchange Discord OAuth2 authorization code for access token and fetch manageable guilds."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        token_resp = await client.post(
            f"{DISCORD_API_ENDPOINT}/oauth2/token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        if token_resp.status_code != 200:
            raise HTTPException(
                status_code=400,
                detail=f"Discord token exchange failed: {token_resp.text}"
            )

        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        auth_headers = {"Authorization": f"Bearer {access_token}"}

        # Fetch current user profile
        user_resp = await client.get(
            f"{DISCORD_API_ENDPOINT}/users/@me",
            headers=auth_headers
        )
        if user_resp.status_code != 200:
            raise HTTPException(
                status_code=400,
                detail="Failed to fetch Discord user profile"
            )
        user_data = user_resp.json()

        # Fetch user's joined guilds
        guilds_resp = await client.get(
            f"{DISCORD_API_ENDPOINT}/users/@me/guilds",
            headers=auth_headers
        )
        if guilds_resp.status_code != 200:
            raise HTTPException(
                status_code=400,
                detail="Failed to fetch Discord user guilds"
            )
        guilds_data = guilds_resp.json()

        # Filter manageable guilds: where user is guild owner OR has Administrator permission (0x8)
        manageable_guild_ids: List[int] = []
        for g in guilds_data:
            is_owner = bool(g.get("owner", False))
            permissions = int(g.get("permissions", 0))
            if is_owner or (permissions & ADMINISTRATOR_PERMISSION) != 0:
                manageable_guild_ids.append(int(g["id"]))

        return {
            "auth_type": "discord",
            "user_id": user_data["id"],
            "username": user_data["username"],
            "avatar": user_data.get("avatar"),
            "is_master_admin": False,
            "guilds": manageable_guild_ids
        }
