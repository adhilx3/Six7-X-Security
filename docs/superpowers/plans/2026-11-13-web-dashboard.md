# Six7 Security Discord Bot - Web Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and deploy a secure, embedded FastAPI web dashboard for Six7 Security Bot that runs inside the existing bot process on Railway with dual authentication (Master Password and Discord OAuth2), server configuration panels, and live bot management.

**Architecture:** Embed a FastAPI web application directly in `bot.py` via `uvicorn.Server` inside the bot's asyncio event loop, sharing the existing SQLite database (`data/six7_security.db`) and live `discord.py` bot instance. Provide server administrators with a modern dark-mode UI (Tailwind CSS + Lucide) to configure Anti-Nuke, Anti-Raid, AutoMod, Verification, and Warnings.

**Tech Stack:** Python 3.10+, FastAPI, Uvicorn, Jinja2, Itdangerous / Starlette SessionMiddleware, HTTPX, SQLite / aiosqlite, Tailwind CSS, Lucide Icons.

**Spec:** [docs/superpowers/specs/2026-11-13-web-dashboard-design.md](file:///C:/Users/adhil.parokkot/.gemini/antigravity/scratch/Six7-X-Security/docs/superpowers/specs/2026-11-13-web-dashboard-design.md)

## Global Constraints

- **Runtime:** Python 3.10+
- **Host & Port:** Listen on `0.0.0.0` and `int(os.getenv("PORT", 8080))` for cloud deployment compatibility on Railway.
- **Framework:** `FastAPI` with `jinja2` templating and `uvicorn` server.
- **Session Security:** Signed cookie sessions via `SessionMiddleware` with `SESSION_SECRET` (fallback to `secrets.token_hex(32)` if unset).
- **Authentication:** Dual auth supporting Master Password (`DASHBOARD_PASSWORD`) and Discord OAuth2 (`identify guilds`).
- **Database Access:** Direct async queries via `utils/database.py` with zero secondary databases or caching layer.
- **Non-blocking Event Loop:** Web server runs concurrently in `asyncio.create_task` inside `bot.py`'s `setup_hook`, never blocking Discord Gateway heartbeats.
- **Test Integrity:** All 34 existing security tests must remain green; all new web modules must be tested with automated unit and integration tests.

## Review Focus

1. **Unauthenticated API Access:** A request to `POST /api/guild/{guild_id}/*` without a valid signed session cookie returns HTTP 401 Unauthorized and does not execute mutations.
2. **Cross-Guild Authorization Bypass:** A user logged in via Discord OAuth2 attempts to modify a guild ID where they do not possess `Administrator` permissions. The endpoint must return HTTP 403 Forbidden.
3. **Invalid Config Input Validation:** Admin submits negative integers or malformed strings for rate limit thresholds or action types. The API must return HTTP 400 Bad Request with a descriptive error message without crashing.
4. **Session Secret Generation Fallback:** When `SESSION_SECRET` is unset in the environment, the app must automatically generate a cryptographically secure random key (`secrets.token_hex(32)`) and continue booting without error.
5. **Discord OAuth2 Failure Resilience:** If the Discord API token exchange fails or returns an error, the callback route must catch the exception, log the failure, and redirect to `/login?error=oauth_failed` instead of failing with an unhandled 500.

---

### Task 1: Web Dependencies & Authentication Infrastructure

**Files:**
- Modify: `requirements.txt`
- Create: `web/__init__.py`
- Create: `web/auth.py`
- Create: `tests/test_web_auth.py`

**Interfaces:**
- Consumes: `os.getenv`, `secrets`, `itsdangerous`, `httpx`
- Produces:
  - `web.auth.verify_password(password: str) -> bool`
  - `web.auth.get_current_user(request: Request) -> dict | None`
  - `web.auth.require_admin(guild_id: int)` dependency
  - `web.auth.get_discord_oauth_url(redirect_uri: str, client_id: str, state: str) -> str`
  - `web.auth.exchange_discord_code(code: str, redirect_uri: str, client_id: str, client_secret: str) -> dict`

- [ ] **Step 1: Update requirements.txt with web dependencies**
Add `fastapi>=0.110.0`, `uvicorn>=0.28.0`, `jinja2>=3.1.0`, `itsdangerous>=2.1.0`, `httpx>=0.27.0`, `python-multipart>=0.0.9`.

- [ ] **Step 2: Write failing unit test in `tests/test_web_auth.py`**
Test password verification against `DASHBOARD_PASSWORD`, session user retrieval, unauthorized rejection, and OAuth2 URL generation.

- [ ] **Step 3: Run test to verify it fails**
Run: `pytest tests/test_web_auth.py -v`
Expected: FAIL with ModuleNotFoundError or ImportError for `web.auth`.

- [ ] **Step 4: Implement `web/__init__.py` and `web/auth.py`**
Implement password checking using constant-time comparison (`secrets.compare_digest`), OAuth2 URL generator, token exchange helper, and FastAPI auth dependency.

- [ ] **Step 5: Run test to verify it passes**
Run: `pytest tests/test_web_auth.py -v`
Expected: PASS

- [ ] **Step 6: Commit**
```bash
git add requirements.txt web/__init__.py web/auth.py tests/test_web_auth.py
git commit -m "feat(web): add web dependencies and authentication infrastructure"
```

---

### Task 2: API Endpoints for Guild Security Configuration

**Files:**
- Create: `web/routes/__init__.py`
- Create: `web/routes/api.py`
- Create: `tests/test_web_api.py`

**Interfaces:**
- Consumes: `web.auth.get_current_user`, `utils.database.db`, `discord.ext.commands.Bot`
- Produces:
  - `api_router = APIRouter(prefix="/api")`
  - `GET /api/health` -> JSON with status, latency, uptime, guilds count
  - `POST /api/guild/{guild_id}/antinuke` -> updates thresholds and punishment
  - `POST /api/guild/{guild_id}/antiraid` -> updates join thresholds, account age, and action
  - `POST /api/guild/{guild_id}/lockdown` -> toggles emergency lockdown
  - `POST /api/guild/{guild_id}/automod` -> updates bad words, scam links, attachments, spam
  - `POST /api/guild/{guild_id}/verification` -> updates verification mode and role ID
  - `POST /api/guild/{guild_id}/whitelist` -> adds/removes whitelist IDs
  - `POST /api/guild/{guild_id}/warnings/delete` -> revokes warning by case ID

- [ ] **Step 1: Write failing unit tests in `tests/test_web_api.py`**
Test health check endpoint, unauthenticated request rejection (401), unauthorized guild rejection (403), valid configuration updates to SQLite database, lockdown toggling, and warning deletion.

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/test_web_api.py -v`
Expected: FAIL with ModuleNotFoundError for `web.routes.api`.

- [ ] **Step 3: Implement `web/routes/__init__.py` and `web/routes/api.py`**
Implement the API router and handlers with input validation, permission enforcement, and calls to `utils.database.db`.

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/test_web_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add web/routes/__init__.py web/routes/api.py tests/test_web_api.py
git commit -m "feat(web): add REST API endpoints for guild security management"
```

---

### Task 3: Dashboard HTML Pages, UI Templates & Static Assets

**Files:**
- Create: `web/static/css/dashboard.css`
- Create: `web/static/js/dashboard.js`
- Create: `web/templates/base.html`
- Create: `web/templates/login.html`
- Create: `web/templates/overview.html`
- Create: `web/templates/guild.html`
- Create: `web/routes/pages.py`
- Create: `tests/test_web_pages.py`

**Interfaces:**
- Consumes: `web.auth.get_current_user`, `utils.database.db`, `discord.ext.commands.Bot`
- Produces:
  - `pages_router = APIRouter()`
  - `GET /` -> renders `overview.html` or redirects to `/login`
  - `GET /login` -> renders `login.html`
  - `POST /login` -> validates password, sets session cookie, redirects to `/`
  - `GET /logout` -> clears session, redirects to `/login`
  - `GET /auth/discord` -> initiates Discord OAuth2 redirect
  - `GET /auth/discord/callback` -> exchanges OAuth2 code and sets session
  - `GET /guild/{guild_id}` -> renders tabbed security management dashboard

- [ ] **Step 1: Write failing tests in `tests/test_web_pages.py`**
Test login page GET/POST, redirect on unauthenticated `/`, rendering of overview with mock guilds, and rendering of `/guild/{guild_id}` with live SQLite configuration.

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/test_web_pages.py -v`
Expected: FAIL with ModuleNotFoundError for `web.routes.pages`.

- [ ] **Step 3: Implement HTML templates and static assets**
Create modern dark-themed templates using Tailwind CSS and Lucide icons:
- `base.html`: Responsive navbar, active server indicator, logout button, toast alert container.
- `login.html`: Master password login form and Discord OAuth2 login button.
- `overview.html`: Server selector cards with icons, member count, security status badge, and bot health stats.
- `guild.html`: Tabbed panels for Anti-Nuke, Anti-Raid, AutoMod, Verification, and Warnings, with interactive sliders, toggles, and tables.
- `dashboard.js`: AJAX settings persistence, banned words tag manager, toast feedback, and emergency lockdown confirmation modal.

- [ ] **Step 4: Implement `web/routes/pages.py`**
Implement the page routes, session cookie management, and template context rendering.

- [ ] **Step 5: Run test to verify it passes**
Run: `pytest tests/test_web_pages.py -v`
Expected: PASS

- [ ] **Step 6: Commit**
```bash
git add web/static/ web/templates/ web/routes/pages.py tests/test_web_pages.py
git commit -m "feat(web): add responsive dashboard UI templates and page routes"
```

---

### Task 4: FastAPI App Factory & Bot Lifecycle Integration

**Files:**
- Create: `web/app.py`
- Modify: `bot.py`
- Modify: `Procfile`
- Modify: `railway.json`
- Create: `tests/test_web_bot_integration.py`

**Interfaces:**
- Consumes: `web.routes.pages.pages_router`, `web.routes.api.api_router`, `bot.py`
- Produces:
  - `web.app.create_app(bot: commands.Bot | None = None) -> FastAPI`
  - Background `uvicorn.Server` task attached to `bot.setup_hook` on `0.0.0.0:$PORT`
  - Graceful server shutdown on `bot.close`

- [ ] **Step 1: Write failing test in `tests/test_web_bot_integration.py`**
Test that `create_app` properly binds `bot` instance to `app.state.bot`, routes are mounted, and the bot setup hook spawns the web task without blocking the asyncio loop.

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/test_web_bot_integration.py -v`
Expected: FAIL with ModuleNotFoundError for `web.app`.

- [ ] **Step 3: Implement `web/app.py`**
Create FastAPI app factory with `SessionMiddleware`, mount static files and routers, store `bot` on `app.state.bot`.

- [ ] **Step 4: Update `bot.py`, `Procfile`, and `railway.json`**
In `bot.py`:
- In `setup_hook`: spawn uvicorn server in `asyncio.create_task` listening on `0.0.0.0` and `PORT`.
- In `close`: signal uvicorn server shutdown.
In `Procfile`:
- Change `worker: python bot.py` to `web: python bot.py`.
In `railway.json`:
- Ensure startup settings align with web service.

- [ ] **Step 5: Run test to verify it passes**
Run: `pytest tests/test_web_bot_integration.py -v`
Expected: PASS

- [ ] **Step 6: Commit**
```bash
git add web/app.py bot.py Procfile railway.json tests/test_web_bot_integration.py
git commit -m "feat(web): integrate FastAPI app into bot lifecycle and configure Railway web service"
```

---

### Task 5: End-to-End Test Suite Verification, Documentation & Deployment

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Run complete test suite**
Run: `pytest -v`
Ensure all existing 34 security tests PLUS all new web dashboard tests pass with 0 failures.

- [ ] **Step 2: Update `README.md`**
Document web dashboard features, environment variables (`DASHBOARD_PASSWORD`, `SESSION_SECRET`, `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`, `DISCORD_REDIRECT_URI`), and Railway deployment instructions.

- [ ] **Step 3: Commit and push to GitHub**
```bash
git add README.md
git commit -m "docs: add web dashboard documentation and deployment instructions"
git push origin main
```

- [ ] **Step 4: Verify deployment readiness**
Confirm git branch is clean and up to date with `origin/main`. Provide the user with clear instructions to enable the public web domain on Railway.

