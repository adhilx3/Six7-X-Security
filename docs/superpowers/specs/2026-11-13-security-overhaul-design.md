# Six7 Security Discord Bot - Complete Security Overhaul Design

## 1. Intent & Why
Six7-X-Security is a Discord security and moderation bot built with `discord.py`. Currently, it provides basic automod, anti-raid, and button-based verification, but lacks critical protections required by modern Discord servers:
- **Zero Anti-Nuke defense**: A compromised administrator account, rogue bot, or disgruntled staff member can wipe all channels, delete roles, ban all members, or invite malicious bots without resistance.
- **AutoMod inaccuracies**: Substring matching creates severe false positives (e.g. banning "ass" blocks "grass", "classic"), and there is no protection against Discord Nitro phishing, token grabbers, or malicious file attachments.
- **Anti-Raid shortcomings**: No channel lockouts, no anti-bot join defense, and no state restoration after raids pass.
- **Storage and reliability**: Synchronous JSON writes block the asyncio event loop and risk data corruption; warnings are ephemeral; and deprecated datetime methods are present.

The purpose of this overhaul is to turn Six7-X-Security into a resilient, enterprise-grade Discord security system with Anti-Nuke, hardened Anti-Raid, intelligent AutoMod, persistent warnings via async SQLite, and robust role-hierarchy moderation.

---

## 2. Goals, Non-Goals, and Anti-Goals

### Goals
- **Full Anti-Nuke Protection**: Monitor Discord audit logs for rapid destructive actions (channel deletion/creation, role deletion/creation, mass bans, mass kicks, unauthorized bot invites, webhook abuse). Strip roles / ban offenders automatically within seconds.
- **Immune Owner & Whitelist**: Server owner is inherently immune; support a granular Anti-Nuke whitelist for trusted co-owners or bots. Keep Anti-Nuke whitelist strictly isolated from AutoMod chat exemptions to prevent privilege escalation.
- **Hardened Anti-Raid**: Implement channel lockdown that toggles `@everyone` send permissions across channels and cleanly restores original states upon unlock. Automatically block/kick unwhitelisted bot joins.
- **Modern AutoMod**:
  - Regex-based word boundaries (`\b`) to eliminate false positives.
  - Phishing / Scam domain detection (fake Nitro links, token stealers, typosquatted domains) with automatic message deletion and immediate timeout.
  - Dangerous executable attachment blocking (`.exe`, `.scr`, `.bat`, `.vbs`, etc.).
  - Duplicate / copypasta spam detection (3 duplicates in 10s) in addition to message-rate spam.
  - Anti-ghostping logging.
- **Async SQLite Data Layer**: Replace `guild_config.json` with `aiosqlite` (`data/six7_security.db`) featuring structured tables for guild configs, persistent warnings, antinuke settings, and whitelists, with automatic legacy JSON migration.
- **Role Hierarchy & Safe Moderation**: Ensure bot and moderator role hierarchy checks prevent permission errors and provide clear feedback. Persistent `/warn`, `/warnings`, `/unwarn`, and `/clearwarnings` commands.
- **Captcha Verification**: Modal verification option with random challenge text alongside standard button verification.
- **Code Modernization**: Replace all deprecated `datetime.utcnow()` with `datetime.datetime.now(datetime.timezone.utc)`.

### Non-Goals
- External web dashboard or REST API (remains entirely managed through Discord slash commands).
- Machine learning/AI natural language toxicity models (reliance on fast, deterministic regex and pattern algorithms to maintain low latency).

### Anti-Goals
- Locking out the server owner or breaking server permissions permanently on false alarms.
- Blocking the asyncio event loop with synchronous file/database I/O.
- Silent failures: any moderation or security trigger must produce visible, structured logs in the configured log channel.

---

## 3. Constraints
- **Library**: `discord.py >= 2.4.0` with `commands.Bot` and `app_commands`.
- **Intents**: Requires `Intents.default()`, `Intents.members = True`, `Intents.message_content = True`.
- **Permissions**: Anti-nuke role stripping and kicking requires the bot's role to be higher in the server role hierarchy than any moderator or managed role, with Administrator or high moderation permissions.
- **Python**: Python 3.10+ compatibility (using timezone-aware datetime objects).
- **Dependencies**: Keep external dependencies minimal: `discord.py`, `python-dotenv`, `aiosqlite`.

---

## 4. Approaches Considered
- **Approach 1: Modern Async SQLite (`aiosqlite`) + Modular Security Engine (Selected)**:
  - Database schema: `guild_config`, `automod_config`, `antiraid_config`, `antinuke_config`, `antinuke_whitelist`, `warnings`, `lockdown_state`.
  - Concurrency-safe, transactional, crash-proof, scales seamlessly.
- **Approach 2: Pure JSON with Thread-Safe Atomic Writes**:
  - Rejected: Complex warning queries, pagination, and high-frequency audit log updates are prone to race conditions and lack relational structure in a single JSON file.

---

## 5. Detailed Component Architecture

### 5.1 Storage Layer (`utils/database.py`)
Replace `utils/storage.py` with an async SQLite manager using `aiosqlite`.
- **Database Path**: `data/six7_security.db`
- **Tables**:
  - `guild_config`:
    - `guild_id INTEGER PRIMARY KEY`
    - `log_channel_id INTEGER`
    - `verification_role_id INTEGER`
    - `verification_channel_id INTEGER`
    - `unverified_role_id INTEGER`
    - `verification_type TEXT DEFAULT 'button'`
  - `automod_config`:
    - `guild_id INTEGER PRIMARY KEY`
    - `enabled INTEGER DEFAULT 1`
    - `banned_words TEXT DEFAULT '[]'` (JSON array)
    - `block_invites INTEGER DEFAULT 1`
    - `invite_whitelist TEXT DEFAULT '[]'` (JSON array)
    - `whitelist_user_ids TEXT DEFAULT '[]'` (JSON array, distinct from anti-nuke whitelist)
    - `whitelist_role_ids TEXT DEFAULT '[]'` (JSON array)
    - `max_mentions INTEGER DEFAULT 5`
    - `max_caps_percent INTEGER DEFAULT 70`
    - `spam_message_count INTEGER DEFAULT 5`
    - `spam_time_window INTEGER DEFAULT 5`
    - `block_scams INTEGER DEFAULT 1`
    - `block_attachments INTEGER DEFAULT 1`
    - `block_duplicates INTEGER DEFAULT 1`
  - `antiraid_config`:
    - `guild_id INTEGER PRIMARY KEY`
    - `enabled INTEGER DEFAULT 1`
    - `join_threshold INTEGER DEFAULT 5`
    - `join_time_window INTEGER DEFAULT 10`
    - `min_account_age_days INTEGER DEFAULT 3`
    - `lockdown_active INTEGER DEFAULT 0`
    - `action_on_raid TEXT DEFAULT 'kick'`
    - `anti_bot_enabled INTEGER DEFAULT 1`
    - `original_verification_level TEXT DEFAULT NULL`
  - `antinuke_config`:
    - `guild_id INTEGER PRIMARY KEY`
    - `enabled INTEGER DEFAULT 1`
    - `max_channel_actions INTEGER DEFAULT 3`
    - `max_role_actions INTEGER DEFAULT 3`
    - `max_member_actions INTEGER DEFAULT 3`
    - `max_webhook_actions INTEGER DEFAULT 3`
    - `action_window_seconds INTEGER DEFAULT 10`
    - `punishment TEXT DEFAULT 'strip_roles'` ('strip_roles' | 'ban' | 'kick')
  - `antinuke_whitelist`:
    - `id INTEGER PRIMARY KEY AUTOINCREMENT`
    - `guild_id INTEGER`
    - `target_id INTEGER`
    - `reason TEXT`
    - `added_by INTEGER`
    - `created_at TEXT`
  - `warnings`:
    - `id INTEGER PRIMARY KEY AUTOINCREMENT`
    - `guild_id INTEGER`
    - `user_id INTEGER`
    - `moderator_id INTEGER`
    - `reason TEXT`
    - `created_at TEXT`
  - `lockdown_state`:
    - `guild_id INTEGER`
    - `channel_id INTEGER`
    - `existed_prior INTEGER` (1 if an overwrite existed, 0 if inherited)
    - `allow_bits INTEGER`
    - `deny_bits INTEGER`
    - `PRIMARY KEY (guild_id, channel_id)`
- **Data Migration**:
  - Automatically checks for `data/guild_config.json`. If found and the SQLite database is empty, it migrates all settings (`automod`, `antiraid`, log/verification roles, and whitelist IDs) directly into the SQLite tables, ensuring zero downtime or loss of prior configuration.

### 5.2 Anti-Nuke Cog (`cogs/antinuke.py`)
- **Audit Log Inspection**:
  - Monitors events:
    - `on_guild_channel_delete`, `on_guild_channel_create`
    - `on_guild_role_delete`, `on_guild_role_create`
    - `on_member_ban`, `on_member_remove` (checks if kicked via audit log)
    - `on_member_join` (bot added check)
    - `on_webhooks_update`
  - Fetches the audit entry with `limit=5`, matching the target ID and ensuring timestamp is within the last 5 seconds.
- **Immunity Boundaries**:
  - Server Owner (`guild.owner_id`) is permanently immune.
  - Whitelisted target IDs (`antinuke_whitelist`) are immune.
  - Bot itself (`bot.user.id`) is immune.
  - Note: AutoMod whitelisted users DO NOT have Anti-Nuke immunity.
- **Sliding-Window Rate Limiting**:
  - In-memory tracker: `dict[guild_id, dict[moderator_id, dict[action_category, deque[float]]]]`.
  - Categories: `channel` (create/delete), `role` (create/delete), `member` (kick/ban), `webhook` (create/delete/modify).
  - If a moderator executes actions exceeding the threshold within `action_window_seconds`:
    - **Trigger Punishment**:
      - `strip_roles`: Removes all roles from the moderator that contain dangerous administrative or moderation permissions (`administrator`, `manage_guild`, `manage_roles`, `manage_channels`, `ban_members`, `kick_members`).
      - `ban`: Bans the offending user.
      - `kick`: Kicks the offending user.
    - **Alert**: Sends a high-priority emergency embed to the log channel and attempts to DM the server owner.
- **Unauthorized Bot Defense**:
  - When a bot joins (`member.bot == True`):
    - Fetches the audit log for `BOT_ADD`.
    - If the inviter is not the server owner and not in `antinuke_whitelist`:
      - Instantly kicks the newly joined bot.
      - Punishes the inviter per `antinuke_config.punishment`.
      - Emits an emergency security alert.

### 5.3 Anti-Raid Cog (`cogs/antiraid.py`)
- **Mass Join Detection**:
  - Sliding window of join timestamps per guild.
  - When threshold is breached: automatically initiates server lockdown.
- **Lockdown Execution**:
  - Sets `lockdown_active = 1` in DB.
  - Records the current server verification level in `antiraid_config.original_verification_level`, then escalates server verification level to `VerificationLevel.high` (or `highest`).
  - Iterates over all guild text channels:
    - Reads existing `@everyone` overwrite.
    - Saves `existed_prior`, `allow_bits`, and `deny_bits` into `lockdown_state`.
    - Updates overwrite to deny `send_messages=False`.
- **Lockdown Release (`/lockdown false`)**:
  - Restores channel overwrites from `lockdown_state`:
    - If `existed_prior == 0`: resets overwrite (`channel.set_permissions(guild.default_role, overwrite=None)`), preserving category inheritance.
    - If `existed_prior == 1`: restores `PermissionOverwrite.from_pair(allow, deny)`.
  - Deletes saved records from `lockdown_state`.
  - Restores the original server verification level recorded prior to the raid.
- **Account Age Policy**:
  - Peacetime: Accounts younger than `min_account_age_days` generate a warning log embed in the log channel.
  - Active Lockdown: Accounts younger than `min_account_age_days` (or all new joins during raid threshold) are immediately kicked or banned according to `action_on_raid`.

### 5.4 AutoMod Cog (`cogs/automod.py`)
- **Word Filter**:
  - Uses `re.compile(rf"\b{re.escape(word)}\b", re.IGNORECASE)` to prevent substring false positives.
  - Basic homoglyph / leetspeak character normalization (e.g., `@` -> `a`, `$` -> `s`).
- **Phishing & Scam Link Blocker**:
  - Matches known phishing patterns (e.g. `discorcl`, `dlscord`, `nitro-free`, `gift-discord`, fake Steam login domains).
  - Action: Immediate message deletion + 1-hour timeout + security log alert.
- **Dangerous File Filter**:
  - Checks `message.attachments`.
  - Blocks executable extensions: `.exe`, `.scr`, `.bat`, `.cmd`, `.vbs`, `.msi`, `.ps1`, `.jar`.
  - Action: Immediate message deletion + user warning DM + log alert.
- **Duplicate / Copypasta Spam**:
  - Tracks the hash of the last 3 messages per user.
  - If 3 identical messages are posted within 10 seconds: deletes the duplicate messages and applies a 10-minute timeout.
- **Anti-Ghostping**:
  - In `on_message_delete`: if a deleted message contained user or role mentions and was posted less than 15 seconds ago, posts a ghostping embed in the log channel with target, author, and content.

### 5.5 Moderation Cog (`cogs/moderation.py`)
- **Hierarchy Guards**:
  - `can_moderate(ctx_or_interaction, target: discord.Member) -> tuple[bool, str]`:
    - Checks `bot_member.top_role > target.top_role` (prevents 403 Forbidden).
    - Checks `moderator.top_role > target.top_role` or `moderator == guild.owner` (prevents mod abuse).
    - Prevents moderation on `guild.owner`.
- **Persistent Warnings**:
  - `/warn member:<Member> reason:<str>`: Inserts into `warnings` table, logs embed, DMs user.
  - `/warnings [member:<Member>]`: Queries and renders formatted embed list with ID, moderator mention, date, and reason.
  - `/unwarn id:<int>`: Deletes warning by ID and notifies moderator.
  - `/clearwarnings member:<Member>`: Removes all warnings for the target user.
- **Modernized Commands**:
  - `/kick`, `/ban [delete_message_days: 0-7]`, `/timeout [minutes: 1-40320]`, `/purge [amount: 1-100]`.
  - Fully timezone-aware UTC timestamps everywhere.

### 5.6 Verification Cog (`cogs/verification.py`)
- **Modes**:
  - `button`: One-click verification button (`VerifyView`).
  - `captcha`: Modal challenge (`CaptchaModal`). Generates a 5-character randomized alphanumeric code (e.g. `A7X9K`), prompts the user to enter it, and verifies match. Blocks automated selfbot button-clickers.
- **Persistence**:
  - `VerifyView` registered in `setup_hook` in `bot.py` with dynamic handling based on guild configuration.

### 5.7 Configuration Cog (`cogs/config_cog.py`)
- **Anti-Nuke Management**:
  - `/antinuke-toggle enabled:<bool>`
  - `/antinuke-config [window_seconds] [channel_actions] [role_actions] [member_actions] [punishment]`
  - `/antinuke-whitelist-add target:<Member|User> [reason]`
  - `/antinuke-whitelist-remove target:<Member|User>`
  - `/antinuke-whitelist-list`
- **AutoMod & Anti-Raid Management**:
  - `/automod-toggle`, `/add-banned-word`, `/remove-banned-word`, `/whitelist-user`, `/whitelist-role`
  - `/antiraid-toggle`, `/set-join-threshold`, `/set-min-account-age`, `/set-raid-action`, `/lockdown state:<bool>`
- **Verification Management**:
  - `/set-verification-mode mode:<Button|Captcha>`
  - `/set-verification-role role:<Role>`
  - `/set-unverified-role role:<Role>`
  - `/setup-verification`
- **Status Overview**:
  - `/security-status`: Displays an all-in-one status dashboard covering Anti-Nuke, Anti-Raid, AutoMod, Logging, and Verification.

---

## 6. What's Left to the Builder (Builder Calls Made)
- **AutoMod Whitelist vs Anti-Nuke Whitelist**: Strictly separated to prevent privilege escalation. AutoMod whitelist only bypasses chat filters; Anti-Nuke whitelist grants server management immunity.
- **Channel Permission Restorations**: Uses `lockdown_state` table storing `existed_prior`, `allow_bits`, and `deny_bits` to ensure channel permissions and category inheritance are cleanly and accurately restored.
- **Account Age Policy**: Peacetime logs suspicious new accounts; active raid/lockdown executes `action_on_raid` (kick/ban).
- **Punishment for Unauthorized Bots**: Added bot is immediately kicked; inviter has dangerous administrative roles stripped.
- **Phishing & Scam Penalty**: Instant message deletion + 1-hour timeout + high-priority log alert.
