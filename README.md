# Discord Security Bot

A modular security/moderation bot built with `discord.py`, featuring:

- **Auto-Mod** — banned word filter, invite link blocking, mass-mention detection, excessive caps detection, spam rate-limiting (with auto-timeout)
- **Anti-Raid** — detects mass joins in a short window, flags/kicks/bans new/suspicious accounts, auto-lockdown mode
- **Verification** — button-based verification panel that grants a role, persists across restarts
- **Logging** — logs message edits/deletes, joins/leaves, bans/unbans, and all mod/automod actions to a channel
- **Manual Moderation** — `/kick`, `/ban`, `/timeout`, `/warn`, `/purge`
- **Slash-command configuration** — no need to edit code or restart the bot to change settings

## 1. Create the bot application

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications) → **New Application**.
2. Go to the **Bot** tab → **Add Bot**.
3. Under **Privileged Gateway Intents**, enable:
   - **Server Members Intent**
   - **Message Content Intent**
4. Copy the **bot token** (Bot tab → Reset Token / Copy).

## 2. Invite the bot to your server

1. Go to **OAuth2 → URL Generator**.
2. Scopes: check `bot` and `applications.commands`.
3. Bot permissions: at minimum check
   `Kick Members`, `Ban Members`, `Moderate Members`, `Manage Messages`, `Manage Roles`,
   `Manage Server` (for lockdown verification-level changes), `View Channels`, `Send Messages`, `Embed Links`, `Read Message History`.
4. Open the generated URL and add the bot to your server.

**Important:** the bot's role must be positioned **above** any roles you want it to manage (e.g. above a "muted" or "unverified" role), and above roles of members you might need to kick/ban.

## 3. Install and configure

```bash
cd security-bot
python -m venv venv
source venv/bin/activate        # on Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# then edit .env and paste your bot token:
# DISCORD_TOKEN=your_token_here
```

## 4. Run the bot

```bash
python bot.py
```

You should see log lines confirming each cog loaded and that slash commands synced. It can take up to an hour for global slash commands to fully propagate the first time (usually much faster).

## 5. Configure your server (as an admin, in Discord)

Run these slash commands in your server:

| Command | Purpose |
|---|---|
| `/set-log-channel #channel` | Where all security logs get sent |
| `/set-verification-role @role` | Role given to members who verify |
| `/setup-verification` | Posts the verify button in the current channel |
| `/automod-toggle enabled:true` | Turn auto-mod on/off |
| `/add-banned-word word:...` | Add to the word filter |
| `/set-max-mentions count:5` | Mass-mention threshold |
| `/whitelist-user user:@someone` | Exempt a user (e.g. other bots) from auto-mod |
| `/antiraid-toggle enabled:true` | Turn anti-raid on/off |
| `/set-join-threshold count:5 seconds:10` | Raid trigger sensitivity |
| `/set-min-account-age days:3` | Accounts younger than this get flagged during a raid |
| `/set-raid-action action:Kick` | Kick / Ban / Log only for suspicious joins during a raid |
| `/lockdown state:true` | Manually toggle lockdown mode |
| `/security-status` | See your full current configuration |

## How it works

- **Storage:** Settings are stored per-server in `data/guild_config.json` (created automatically). This is fine for small-to-mid servers; swap in SQLite/Postgres in `utils/storage.py` if you need heavier scale or multiple bot instances.
- **Anti-raid logic:** Tracks join timestamps per server in memory. If the number of joins within the configured window crosses the threshold, it flips on `lockdown_active`, raises the server's verification level, and starts auto-kicking/banning new accounts younger than the configured minimum age until you turn lockdown off with `/lockdown state:false`.
- **Verification:** Uses a Discord UI `Button` with a persistent `custom_id`, registered in the cog's `__init__`, so it keeps working even after the bot restarts (no need to re-post the panel).
- **Auto-mod:** Runs on every non-bot message; checks banned words → invite links → mass mentions → caps % → message-rate spam (which also applies a 10-minute timeout on trip).

## Extending it

- Add new filters inside `cogs/automod.py` — follow the existing pattern of checking a setting, then calling `self._take_action(...)`.
- Add new slash-command settings inside `cogs/config_cog.py`, then use `get_guild_config()` in whichever cog needs to read them.
- Everything mod-related that should be visible to admins should go through `send_log()` in `cogs/logging_cog.py`, so it always lands in the same log channel.

## Notes & limitations

- `message_content` intent must be enabled both in the Developer Portal **and** in `bot.py` (already done here) — required for the word filter and caps checks to see message text.
- The bot needs `Manage Server` permission to auto-raise verification level during a raid; without it, lockdown still works (kicking/banning new joins) but won't touch the server's verification level.
- This is a single-process bot with JSON storage — good for one to a handful of servers. For a public multi-server bot at scale, move to a real database and consider sharding.
