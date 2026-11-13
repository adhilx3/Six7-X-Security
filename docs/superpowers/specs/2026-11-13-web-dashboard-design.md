# Six7 Security Discord Bot - Web Dashboard Design Specification

## 1. Intent & Why
Six7-X-Security currently protects servers via Discord slash commands (`/antinuke-config`, `/lockdown`, `/automod-toggle`, etc.). While slash commands are powerful for in-chat operations, server administrators need a visual, centralized web dashboard to:
- Quickly review security posture, bot uptime, and system status across all protected servers.
- Configure Anti-Nuke thresholds, action limits, and whitelist trusted staff without typing long commands.
- Visually toggle Anti-Raid settings, inspect raid sensitivity, and trigger emergency channel lockouts with a single click.
- Manage AutoMod word filters with visual tag inputs, toggle phishing/file shields, and inspect spam rate settings.
- Search, view, and revoke persistent member warnings.

This specification details an embedded **FastAPI** web dashboard that runs asynchronously within the bot process on Railway, directly sharing the existing SQLite database (`data/six7_security.db`) and Discord client instance with zero network overhead.

---

## 2. Goals, Non-Goals, and Anti-Goals

### Goals
- **Embedded Web Server**: Launch a FastAPI application alongside the Discord bot using `uvicorn` on `0.0.0.0:$PORT` (compatible with Railway's automatic port assignment).
- **Dual Authentication**:
  - **Master Password Login**: Immediate password-based login using `DASHBOARD_PASSWORD` from environment variables, enabling zero-configuration access for the bot owner.
  - **Discord OAuth2**: Allows guild administrators to log in with their Discord accounts, automatically discovering and authorizing them for servers where they hold `Administrator` permissions.
- **Interactive Security Dashboard**:
  - **Global Overview (`/`)**: Displays active guilds, bot latency, uptime, and high-level security stats.
  - **Guild Security Panel (`/guild/{guild_id}`)**:
    - **Anti-Nuke Tab**: Sliders/inputs for rate limits (channel, role, member, webhook actions), punishment selector (`strip_roles`, `ban`, `kick`), and interactive whitelist table (add/remove trusted IDs).
    - **Anti-Raid Tab**: Emergency Lockdown toggle button, join threshold and window inputs, minimum account age slider, and raid action selector.
    - **AutoMod Tab**: Tag-based banned words manager, scam/phishing link shield toggle, executable attachment toggle, and spam rate thresholds.
    - **Verification Tab**: Toggle between Button Click and Captcha Challenge, role assignments, and panel status.
    - **Warnings & Moderation Tab**: Searchable table of member warnings with one-click revocation (`unwarn`).
- **Modern Dark UI**: Designed with Tailwind CSS and Lucide icons, mobile-responsive and styled to match Discord's aesthetic.

### Non-Goals
- Real-time WebSockets for chat monitoring (standard HTTP endpoints and responsive UI are sufficient for configuration and log inspection).
- Multi-tenant billing / payment gateways (free/open-source security tool).

### Anti-Goals
- Blocking the Discord bot's asyncio event loop (all web requests must use asynchronous I/O and async database calls).
- Requiring a secondary database or external caching layer (FastAPI directly queries `utils/database.py`).
- Security bypasses: Unauthenticated users must not view or edit guild configuration.

---

## 3. Constraints
- **Framework**: `FastAPI` with `jinja2` templating and `uvicorn` server.
- **Runtime**: Runs on the same Python 3.10+ process as `discord.py` via `asyncio.create_task` or uvicorn Server.
- **Port**: Listens on `os.getenv("PORT", 8080)` and host `0.0.0.0` for cloud deployment compatibility on Railway.
- **Security**: Signed cookie sessions (`itsdangerous` / `SessionMiddleware`) with CSRF protection on mutation endpoints.
- **Dependencies**: `fastapi`, `uvicorn`, `jinja2`, `itsdangerous`, `httpx` (for Discord OAuth2 token exchange).

---

## 4. Approaches Considered

- **Approach 1: Embedded FastAPI Web Server (Selected)**:
  - Single process running both Discord bot and FastAPI web server.
  - Direct async access to `bot` instance and SQLite database.
  - Zero deployment friction: Railway exposes the port automatically via `Generate Domain`.
- **Approach 2: Separate Next.js App on Vercel**:
  - Requires maintaining two separate repos, configuring CORS, and exposing public bot REST APIs with API tokens.
  - Rejected: Overcomplicated architecture for an open-source security bot with unnecessary multi-host latency.

---

## 5. Detailed Component Architecture

### 5.1 Web Application Structure (`web/`)
```
web/
├── __init__.py
├── app.py             # FastAPI application, route handlers, auth logic
├── static/
│   ├── css/
│   │   └── custom.css # Minor styling enhancements
│   └── js/
│       └── main.js    # Interactive UI handlers (tag input, AJAX settings saving)
└── templates/
    ├── base.html      # Common layout with dark theme, sidebar, notifications
    ├── login.html     # Login page (Password & Discord OAuth2 buttons)
    ├── overview.html  # Server selection & bot health metrics
    └── guild.html     # Tabbed server security management interface
```

### 5.2 Authentication Flow
- **Session Cookie**: Encrypted with `SECRET_KEY` (auto-generated or loaded from `SESSION_SECRET`).
- **Authentication Check**: Dependency `get_current_user` checks session:
  - If authenticated via password: user marked as `is_master_admin = True` (can manage all guilds the bot is in).
  - If authenticated via Discord OAuth2: session stores `user_id` and list of `manageable_guild_ids` (guilds where the user has `Administrator` permissions).
- **Login Routes**:
  - `GET /login`: Renders login template.
  - `POST /login`: Validates submitted password against `DASHBOARD_PASSWORD`.
  - `GET /auth/discord`: Redirects to Discord OAuth2 URL (`identify guilds`).
  - `GET /auth/discord/callback`: Exchanges OAuth2 code with Discord API via `httpx`, fetches user profile and user's guilds, stores authorized guild IDs in session, redirects to `/`.
  - `GET /logout`: Clears session and redirects to `/login`.

### 5.3 Route & API Endpoints
- **Pages**:
  - `GET /`: Renders `overview.html` listing accessible guilds and bot stats (ping, uptime, guilds count).
  - `GET /guild/{guild_id}`: Renders `guild.html` with configuration for Anti-Nuke, Anti-Raid, AutoMod, Verification, and Warnings.
- **Action Endpoints (JSON API)**:
  - `POST /api/guild/{guild_id}/antinuke`: Updates thresholds and punishment.
  - `POST /api/guild/{guild_id}/antiraid`: Updates join threshold, window, account age, raid action.
  - `POST /api/guild/{guild_id}/lockdown`: Toggles server lockdown state.
  - `POST /api/guild/{guild_id}/automod`: Updates word list, scam toggle, attachment toggle, spam limits.
  - `POST /api/guild/{guild_id}/verification`: Updates verification mode (`button` or `captcha`) and roles.
  - `POST /api/guild/{guild_id}/whitelist`: Adds or removes an Anti-Nuke whitelisted user/bot ID.
  - `POST /api/guild/{guild_id}/warnings/delete`: Deletes a specific warning by case ID.
  - `GET /api/health`: Healthcheck endpoint for Railway (returns status, bot latency, uptime).

### 5.4 Bot Lifecycle Integration (`bot.py`)
In `bot.py`:
- In `setup_hook`:
  - Starts the FastAPI server as a non-blocking asyncio task using `uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=PORT, loop="asyncio"))`.
  - Stores `bot` reference on `app.state.bot` so web endpoints can inspect bot channels, roles, and guilds in real time.

---

## 6. What's Left to the Builder
- Selection of specific color accents and dashboard styling details (dark slate and blurple accents).
- Session secret generation fallback (`secrets.token_hex(32)` if not specified in environment).
- Default dashboard password fallback with logged warning if unset.

