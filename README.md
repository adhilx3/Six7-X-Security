# Six7 Security Discord Bot 🛡️

A high-performance, modular security, anti-nuke, and moderation bot built with `discord.py` and `aiosqlite`.

---

## Features

### 🛡️ Anti-Nuke Defense Engine
- **Audit Log Inspection**: Monitors channel creation/deletion, role creation/deletion, kicks, bans, webhook modifications, and bot additions in real-time.
- **Sliding-Window Rate Limiting**: Detects rogue administrators or compromised accounts attempting destructive actions in short bursts.
- **Punitive Actions**: Automatically strips dangerous administrative permissions/roles (`administrator`, `manage_guild`, `manage_roles`, `manage_channels`, `ban_members`, `kick_members`) or kicks/bans the offender.
- **Anti-Bot Join Protection**: Automatically kicks unauthorized bots invited by non-owners and strips dangerous roles from the inviter.
- **Immunity System**: Server owner is permanently immune, with support for an independent Anti-Nuke whitelist for trusted co-owners or bots.

### 🚨 Hardened Anti-Raid & Lockdown
- **Mass Join Detection**: Automatically tracks join velocity within configurable sliding windows.
- **Smart Channel Lockdown**: Automatically sets `@everyone` to `send_messages=False` across all public text channels while **persisting original permission states**.
- **Clean State Restoration**: When `/lockdown state:false` is executed, channels that originally had no override cleanly revert to category inheritance (no broken empty overwrites), and channels with prior custom permissions revert to their exact previous state.
- **Verification Escalation & Restore**: Temporarily raises server verification level during raids and restores previous level upon unlock.
- **New Account Enforcement**: Flags suspicious new accounts during peacetime, and automatically kicks/bans them during active raids or lockdowns.

### 🤖 Intelligent Auto-Mod
- **Regex Word Boundaries (`\b`)**: Eliminates false positives (e.g. banning `ass` will never block words like `grass`, `classic`, or `compass`).
- **Homoglyph / Leetspeak Normalization**: Catches obfuscated bypasses like `a$$`, `@ss`, `cl@ssic`.
- **Phishing & Scam Link Blocker**: Detects fake Discord Nitro scams, token grabbers, and typosquatted domains (e.g. `discorcl.gift`, `dlscord.app`, `steamcommunity-tradeoffer.gift`) with instant message deletion and a 1-hour timeout.
- **Dangerous File Attachment Blocker**: Detects and deletes malicious executables (`.exe`, `.scr`, `.bat`, `.cmd`, `.vbs`, `.msi`, `.ps1`, `.jar`) and warns the uploader.
- **Duplicate / Copypasta Spam**: Detects identical messages repeated across channels and applies automatic timeouts.
- **Anti-Ghostping Logger**: Detects deleted messages containing user or role mentions within 15 seconds of posting and logs the author, channel, and content.
- **Invite & Mass Mention Blocking**: Detects disguised and raw Discord server invites and mass mentions.

### 🔨 Hierarchy-Safe Moderation & Persistent Warnings
- **Role Hierarchy Protection**: Prevents moderators or the bot from executing actions against members with equal or higher roles, or the server owner.
- **Persistent Warning History**: Backed by SQLite; warnings survive bot restarts and provide full auditability (`/warn`, `/warnings`, `/unwarn`, `/clearwarnings`).
- **Comprehensive Moderation Commands**: `/kick`, `/ban` (with message history deletion presets), `/timeout`, `/warn`, `/purge`.

### 🔒 Verification (Button & Captcha Modal)
- **Button Verification**: One-click verification panel granting a verified role and removing an unverified role.
- **Captcha Challenge**: Randomized 5-character alphanumeric challenge modal requiring user input to defeat automated raid selfbots.
- **Persistent View**: Registered in `setup_hook` to ensure buttons and modals continue working seamlessly across bot restarts.

### 💾 Async SQLite Database (`aiosqlite`)
- Replaces legacy JSON storage with crash-safe, transaction-backed SQLite (`data/six7_security.db`).
- **Automatic Migration**: Seamlessly imports existing `data/guild_config.json` on first run without manual intervention.

---

## 1. Setup Discord Developer Application

1. Open the [Discord Developer Portal](https://discord.com/developers/applications) → **New Application**.
2. Navigate to the **Bot** tab → **Add Bot**.
3. Under **Privileged Gateway Intents**, enable:
   - **Server Members Intent** (required for join/leave events, anti-raid, and anti-nuke).
   - **Message Content Intent** (required for automod scanning).
4. Copy the **Bot Token**.

---

## 2. Invite Bot to Server

1. Navigate to **OAuth2 → URL Generator**.
2. Check `bot` and `applications.commands`.
3. Check required permissions:
   `Administrator` (recommended for full Anti-Nuke role stripping and channel lockdowns), or at minimum:
   `Manage Server`, `Manage Roles`, `Manage Channels`, `Kick Members`, `Ban Members`, `Moderate Members`, `Manage Messages`, `View Audit Log`, `View Channels`, `Send Messages`, `Embed Links`, `Read Message History`.
4. Open the generated URL and invite the bot.
5. **Role Hierarchy**: In Server Settings → Roles, drag the bot's role **above** all moderator, member, and unverified roles.

---

## 3. Installation & Run

```bash
git clone https://github.com/adhilx3/Six7-X-Security.git
cd Six7-X-Security

# Create virtual environment
python -m venv venv
source venv/bin/activate        # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and paste your DISCORD_TOKEN
```

Run the bot:
```bash
python bot.py
```

---

## 4. Slash Command Reference

### Anti-Nuke Commands
| Command | Description |
|---|---|
| `/antinuke-toggle enabled:<bool>` | Turn Anti-Nuke defense on/off |
| `/antinuke-config` | Configure action window, thresholds for channels/roles/members, and punishment (`strip_roles`, `ban`, `kick`) |
| `/antinuke-whitelist-add target:<User> [reason]` | Add a trusted user or bot to Anti-Nuke immunity |
| `/antinuke-whitelist-remove target:<User>` | Remove an account from Anti-Nuke immunity |
| `/antinuke-whitelist-list` | View all Anti-Nuke whitelisted accounts |

### Anti-Raid & Lockdown Commands
| Command | Description |
|---|---|
| `/antiraid-toggle enabled:<bool>` | Turn Anti-Raid mass-join detection on/off |
| `/set-join-threshold count:<int> seconds:<int>` | Adjust join velocity sensitivity |
| `/set-min-account-age days:<int>` | Minimum account age to bypass raid action |
| `/set-raid-action action:<Kick\|Ban\|Log only>` | Action for suspicious accounts during raids |
| `/lockdown state:<bool>` | Toggle server lockdown mode (locks/restores public channel permissions) |

### Auto-Mod Commands
| Command | Description |
|---|---|
| `/automod-toggle enabled:<bool>` | Turn Auto-Mod filtering on/off |
| `/add-banned-word word:<str>` | Add a phrase to the word boundary filter |
| `/remove-banned-word word:<str>` | Remove a phrase from the word filter |
| `/set-max-mentions count:<int>` | Set maximum mentions allowed per message |
| `/whitelist-user user:<Member>` | Exempt a user from AutoMod chat checks |
| `/whitelist-role role:<Role>` | Exempt a role from AutoMod chat checks |
| `/automod-scam-toggle enabled:<bool>` | Toggle phishing & fake Nitro scam blocker |
| `/automod-attachments-toggle enabled:<bool>` | Toggle executable file blocker |

### Moderation & Warning Commands
| Command | Description |
|---|---|
| `/warn member:<Member> reason:<str>` | Issue a formal warning and persist in SQLite |
| `/warnings [member:<Member>]` | View warning history for a user or the entire guild |
| `/unwarn warning_id:<int>` | Delete a warning case by ID |
| `/clearwarnings member:<Member>` | Clear all warnings for a user |
| `/kick member:<Member> [reason]` | Kick a member (with hierarchy checks) |
| `/ban member:<Member> [delete_days] [reason]` | Ban a member with message history purge |
| `/timeout member:<Member> minutes:<int> [reason]` | Timeout a member |
| `/purge amount:<1-100>` | Bulk delete recent channel messages |

### Setup & Status Commands
| Command | Description |
|---|---|
| `/set-log-channel channel:<TextChannel>` | Set channel where all security logs are delivered |
| `/set-verification-mode mode:<Button\|Captcha>` | Choose between button or captcha modal verification |
| `/set-verification-role role:<Role>` | Role granted upon passing verification |
| `/set-unverified-role role:<Role>` | Role automatically assigned to new joins until verified |
| `/setup-verification` | Post the persistent verification panel in the current channel |
| `/security-status` | View full dashboard of all security modules, thresholds, and statistics |

---

## 5. Running Tests

Run the full automated test suite:
```bash
pytest -v
```
