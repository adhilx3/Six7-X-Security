# Six7 Security Discord Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform Six7-X-Security into a comprehensive, enterprise-grade Discord security system with full Anti-Nuke protection, hardened Anti-Raid with channel lockouts, intelligent regex/phishing AutoMod, persistent SQLite warnings, role-hierarchy checks, and captcha verification.

**Architecture:** Replace the synchronous JSON storage with an asynchronous SQLite database (`data/six7_security.db`) managed via `aiosqlite` with automatic legacy migration. Implement an event-driven `AntiNuke` cog with audit log monitoring and rate-limited punitive role stripping/banning. Harden `AutoMod` with regex word boundaries, phishing detection, dangerous file scanning, duplicate spam filters, and anti-ghostping detection. Upgrade `AntiRaid` with permission-reverting channel lockouts, and modernize `Moderation` with hierarchy checks and persistent warnings.

**Tech Stack:** Python 3.10+, `discord.py >= 2.4.0`, `aiosqlite >= 0.20.0`, `python-dotenv >= 1.0.0`, `pytest >= 8.0.0`, `pytest-asyncio >= 0.23.0`.

**Spec:** [docs/superpowers/specs/2026-11-13-security-overhaul-design.md](file:///C:/Users/adhil.parokkot/.gemini/antigravity/scratch/Six7-X-Security/docs/superpowers/specs/2026-11-13-security-overhaul-design.md)

## Global Constraints

- Python timezone-aware datetimes: Replace all `datetime.datetime.utcnow()` with `datetime.datetime.now(datetime.timezone.utc)`.
- Anti-Nuke immunity: Guild owner (`guild.owner_id`) is permanently immune; AutoMod chat whitelist must remain completely isolated from Anti-Nuke server management immunity.
- Discord permissions: Bot role must be higher than target roles to execute moderation/role-stripping actions; always catch `discord.Forbidden`.
- Channel permissions: Preserve original `@everyone` overwrite states (`existed_prior`, `allow_bits`, `deny_bits`) so lockdown release retains category inheritance.
- Non-blocking I/O: All database operations must be async (`aiosqlite`).

## Review Focus

- Substring false positives in word filter (e.g. "grass", "classic" containing "ass") must never trigger AutoMod violations.
- Phishing link regex must detect typosquatted domains (`discorcl.gift`, `dlscord.app`, `steamcommunlty.com`) and not legitimate `discord.com` or `discord.gg`.
- Lockdown release must not leave empty overwrites on channels that previously inherited `@everyone` permissions.
- In-memory rate limiting sliding windows must discard timestamps older than `action_window_seconds` to prevent memory leaks.
- Database migration must cleanly import existing `data/guild_config.json` without data loss or duplicate key errors.

---

### Task 1: Async SQLite Database Layer (`utils/database.py`)

**Files:**
- Create: `utils/database.py`
- Modify: `requirements.txt:1-2`
- Test: `tests/test_database.py`

**Interfaces:**
- Consumes: `data/guild_config.json` (if present for legacy migration)
- Produces:
  - `async def init_db(db_path: str = None) -> aiosqlite.Connection`
  - `async def get_guild_config(guild_id: int) -> dict`
  - `async def update_guild_config(guild_id: int, **kwargs) -> None`
  - `async def get_automod_config(guild_id: int) -> dict`
  - `async def update_automod_config(guild_id: int, **kwargs) -> None`
  - `async def get_antiraid_config(guild_id: int) -> dict`
  - `async def update_antiraid_config(guild_id: int, **kwargs) -> None`
  - `async def get_antinuke_config(guild_id: int) -> dict`
  - `async def update_antinuke_config(guild_id: int, **kwargs) -> None`
  - `async def is_antinuke_whitelisted(guild_id: int, target_id: int) -> bool`
  - `async def add_antinuke_whitelist(guild_id: int, target_id: int, reason: str, added_by: int) -> None`
  - `async def remove_antinuke_whitelist(guild_id: int, target_id: int) -> bool`
  - `async def get_antinuke_whitelist(guild_id: int) -> list[dict]`
  - `async def add_warning(guild_id: int, user_id: int, moderator_id: int, reason: str) -> int`
  - `async def get_warnings(guild_id: int, user_id: int = None) -> list[dict]`
  - `async def delete_warning(warning_id: int) -> bool`
  - `async def clear_warnings(guild_id: int, user_id: int) -> int`
  - `async def save_channel_lockdown_state(guild_id: int, channel_id: int, existed_prior: bool, allow_bits: int, deny_bits: int) -> None`
  - `async def get_lockdown_states(guild_id: int) -> list[dict]`
  - `async def clear_lockdown_states(guild_id: int) -> None`

- [ ] **Step 1: Update requirements.txt with aiosqlite and test dependencies**
- [ ] **Step 2: Write failing tests in `tests/test_database.py` covering schema creation, migrations, CRUD, warnings, and whitelisting**
- [ ] **Step 3: Run pytest to verify tests fail**
- [ ] **Step 4: Implement `utils/database.py`**
- [ ] **Step 5: Run pytest to verify tests pass**
- [ ] **Step 6: Commit Task 1**

---

### Task 2: Anti-Nuke Engine Cog (`cogs/antinuke.py`)

**Files:**
- Create: `cogs/antinuke.py`
- Test: `tests/test_antinuke.py`

**Interfaces:**
- Consumes: `utils/database.py` (`get_antinuke_config`, `is_antinuke_whitelisted`, `get_guild_config`), `cogs/logging_cog.py` (`send_log`)
- Produces: `AntiNuke(commands.Cog)` handling audit logs for channels, roles, kicks, bans, bots, webhooks, sliding window rate-limiting, and punitive role stripping/banning.

- [ ] **Step 1: Write failing tests in `tests/test_antinuke.py` simulating audit log events, rate-limit thresholds, immunity checks, and punishments**
- [ ] **Step 2: Run pytest to verify tests fail**
- [ ] **Step 3: Implement `cogs/antinuke.py` with sliding window rate limiting, audit log fetchers, immunity boundaries, role stripping, and unwhitelisted bot eviction**
- [ ] **Step 4: Run pytest to verify tests pass**
- [ ] **Step 5: Commit Task 2**

---

### Task 3: Anti-Raid & Channel Lockdown Upgrades (`cogs/antiraid.py`)

**Files:**
- Modify: `cogs/antiraid.py:1-89`
- Test: `tests/test_antiraid.py`

**Interfaces:**
- Consumes: `utils/database.py` (`get_antiraid_config`, `update_antiraid_config`, `save_channel_lockdown_state`, `get_lockdown_states`, `clear_lockdown_states`), `cogs/logging_cog.py` (`send_log`)
- Produces: Upgraded `AntiRaid(commands.Cog)` with full channel permission lock/restore, server verification level preservation, and peacetime vs active lockdown account age enforcement.

- [ ] **Step 1: Write failing tests in `tests/test_antiraid.py` testing channel lockdown permission recording, category inheritance preservation on unlock, and join rate limiting**
- [ ] **Step 2: Run pytest to verify tests fail**
- [ ] **Step 3: Implement channel lockdown and unlock logic, verification level backup/restore, and account age enforcement in `cogs/antiraid.py`**
- [ ] **Step 4: Run pytest to verify tests pass**
- [ ] **Step 5: Commit Task 3**

---

### Task 4: AutoMod Hardening & Content Protection (`cogs/automod.py`)

**Files:**
- Modify: `cogs/automod.py:1-125`
- Test: `tests/test_automod.py`

**Interfaces:**
- Consumes: `utils/database.py` (`get_automod_config`), `cogs/logging_cog.py` (`send_log`)
- Produces: Hardened `AutoMod(commands.Cog)` with `\b` regex word boundaries, phishing pattern matcher, dangerous file attachment blocker, duplicate message spam detector, and anti-ghostping listener.

- [ ] **Step 1: Write failing tests in `tests/test_automod.py` testing regex word boundaries (ensuring "grass" is not blocked by "ass"), scam domain detection, dangerous file extensions, duplicate spam, and ghostping detection**
- [ ] **Step 2: Run pytest to verify tests fail**
- [ ] **Step 3: Implement regex word boundary filtering, scam domain detection, file attachment scanning, duplicate message tracking, and ghostping detection in `cogs/automod.py`**
- [ ] **Step 4: Run pytest to verify tests pass**
- [ ] **Step 5: Commit Task 4**

---

### Task 5: Moderation Cog Overhaul with Persistent Warnings (`cogs/moderation.py`)

**Files:**
- Modify: `cogs/moderation.py:1-94`
- Test: `tests/test_moderation.py`

**Interfaces:**
- Consumes: `utils/database.py` (`add_warning`, `get_warnings`, `delete_warning`, `clear_warnings`), `cogs/logging_cog.py` (`send_log`)
- Produces: Modernized `Moderation(commands.Cog)` with role hierarchy verification (`can_moderate`), persistent `/warn`, `/warnings`, `/unwarn`, `/clearwarnings`, and timezone-aware UTC datetime.

- [ ] **Step 1: Write failing tests in `tests/test_moderation.py` testing hierarchy check rules, warning insertion, deletion, and query formatting**
- [ ] **Step 2: Run pytest to verify tests fail**
- [ ] **Step 3: Implement hierarchy checks, warnings commands, and timezone-aware datetime updates in `cogs/moderation.py`**
- [ ] **Step 4: Run pytest to verify tests pass**
- [ ] **Step 5: Commit Task 5**

---

### Task 6: Verification Modes & Captcha Challenge (`cogs/verification.py`)

**Files:**
- Modify: `cogs/verification.py:1-119`
- Test: `tests/test_verification.py`

**Interfaces:**
- Consumes: `utils/database.py` (`get_guild_config`, `update_guild_config`), `cogs/logging_cog.py` (`send_log`)
- Produces: Upgraded `Verification(commands.Cog)` supporting both standard button click (`VerifyView`) and interactive modal challenge (`CaptchaModal`), with dynamic view dispatching.

- [ ] **Step 1: Write failing tests in `tests/test_verification.py` testing captcha generation, code verification matching, and role assignment logic**
- [ ] **Step 2: Run pytest to verify tests fail**
- [ ] **Step 3: Implement `CaptchaModal` and dynamic verification dispatching in `cogs/verification.py`**
- [ ] **Step 4: Run pytest to verify tests pass**
- [ ] **Step 5: Commit Task 6**

---

### Task 7: Configuration Cog, Bot Integration & Documentation (`cogs/config_cog.py`, `bot.py`, `README.md`)

**Files:**
- Modify: `cogs/config_cog.py:1-161`
- Modify: `bot.py:1-61`
- Modify: `README.md:1-90`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: All updated cogs and `utils/database.py`
- Produces:
  - New slash commands in `cogs/config_cog.py` for Anti-Nuke toggles, thresholds, whitelisting, and `/security-status`.
  - Updated `bot.py` loading `cogs.antinuke`, initializing the SQLite database in `setup_hook`, and registering persistent views.
  - Comprehensive documentation in `README.md`.

- [ ] **Step 1: Write failing tests in `tests/test_config.py` testing anti-nuke slash commands, whitelist commands, and configuration persistence**
- [ ] **Step 2: Run pytest to verify tests fail**
- [ ] **Step 3: Implement new configuration slash commands in `cogs/config_cog.py`, integrate `init_db` and `cogs.antinuke` in `bot.py`, and update `README.md`**
- [ ] **Step 4: Run full test suite across all modules**
- [ ] **Step 5: Commit Task 7**

