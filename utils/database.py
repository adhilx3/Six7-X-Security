import datetime
import json
import os
import aiosqlite

DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "six7_security.db"
)
DEFAULT_JSON_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "guild_config.json"
)


def _get_db_path(db_path: str = None) -> str:
    return db_path or DEFAULT_DB_PATH


async def init_db(db_path: str = None):
    path = _get_db_path(db_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    async with aiosqlite.connect(path) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS guild_config (
                guild_id INTEGER PRIMARY KEY,
                log_channel_id INTEGER,
                verification_role_id INTEGER,
                verification_channel_id INTEGER,
                unverified_role_id INTEGER,
                verification_type TEXT DEFAULT 'button'
            );
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS automod_config (
                guild_id INTEGER PRIMARY KEY,
                enabled INTEGER DEFAULT 1,
                banned_words TEXT DEFAULT '[]',
                block_invites INTEGER DEFAULT 1,
                invite_whitelist TEXT DEFAULT '[]',
                whitelist_user_ids TEXT DEFAULT '[]',
                whitelist_role_ids TEXT DEFAULT '[]',
                max_mentions INTEGER DEFAULT 5,
                max_caps_percent INTEGER DEFAULT 70,
                spam_message_count INTEGER DEFAULT 5,
                spam_time_window INTEGER DEFAULT 5,
                block_scams INTEGER DEFAULT 1,
                block_attachments INTEGER DEFAULT 1,
                block_duplicates INTEGER DEFAULT 1
            );
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS antiraid_config (
                guild_id INTEGER PRIMARY KEY,
                enabled INTEGER DEFAULT 1,
                join_threshold INTEGER DEFAULT 5,
                join_time_window INTEGER DEFAULT 10,
                min_account_age_days INTEGER DEFAULT 3,
                lockdown_active INTEGER DEFAULT 0,
                action_on_raid TEXT DEFAULT 'kick',
                anti_bot_enabled INTEGER DEFAULT 1,
                original_verification_level TEXT DEFAULT NULL
            );
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS antinuke_config (
                guild_id INTEGER PRIMARY KEY,
                enabled INTEGER DEFAULT 1,
                max_channel_actions INTEGER DEFAULT 3,
                max_role_actions INTEGER DEFAULT 3,
                max_member_actions INTEGER DEFAULT 3,
                max_webhook_actions INTEGER DEFAULT 3,
                action_window_seconds INTEGER DEFAULT 10,
                punishment TEXT DEFAULT 'strip_roles'
            );
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS antinuke_whitelist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                reason TEXT,
                added_by INTEGER,
                created_at TEXT,
                UNIQUE(guild_id, target_id)
            );
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                reason TEXT,
                created_at TEXT
            );
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS lockdown_state (
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                existed_prior INTEGER DEFAULT 0,
                allow_bits INTEGER DEFAULT 0,
                deny_bits INTEGER DEFAULT 0,
                PRIMARY KEY (guild_id, channel_id)
            );
        """)
        await db.commit()


# ---------- Guild Config ----------

async def get_guild_config(guild_id: int, db_path: str = None) -> dict:
    path = _get_db_path(db_path)
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM guild_config WHERE guild_id = ?", (guild_id,)) as cur:
            row = await cur.fetchone()
            if row:
                return dict(row)
            await db.execute("INSERT OR IGNORE INTO guild_config (guild_id) VALUES (?)", (guild_id,))
            await db.commit()
        async with db.execute("SELECT * FROM guild_config WHERE guild_id = ?", (guild_id,)) as cur:
            row = await cur.fetchone()
            return dict(row)


async def update_guild_config(guild_id: int, db_path: str = None, **kwargs):
    if not kwargs:
        return
    path = _get_db_path(db_path)
    await get_guild_config(guild_id, db_path=path)
    set_clause = ", ".join(f"{k} = ?" for k in kwargs.keys())
    values = list(kwargs.values()) + [guild_id]
    async with aiosqlite.connect(path) as db:
        await db.execute(f"UPDATE guild_config SET {set_clause} WHERE guild_id = ?", values)
        await db.commit()


# ---------- AutoMod Config ----------

def _parse_automod_row(row: dict) -> dict:
    d = dict(row)
    for col in ("banned_words", "invite_whitelist", "whitelist_user_ids", "whitelist_role_ids"):
        if isinstance(d.get(col), str):
            try:
                d[col] = json.loads(d[col])
            except json.JSONDecodeError:
                d[col] = []
    return d


async def get_automod_config(guild_id: int, db_path: str = None) -> dict:
    path = _get_db_path(db_path)
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM automod_config WHERE guild_id = ?", (guild_id,)) as cur:
            row = await cur.fetchone()
            if row:
                return _parse_automod_row(dict(row))
            await db.execute("INSERT OR IGNORE INTO automod_config (guild_id) VALUES (?)", (guild_id,))
            await db.commit()
        async with db.execute("SELECT * FROM automod_config WHERE guild_id = ?", (guild_id,)) as cur:
            row = await cur.fetchone()
            return _parse_automod_row(dict(row))


async def update_automod_config(guild_id: int, db_path: str = None, **kwargs):
    if not kwargs:
        return
    path = _get_db_path(db_path)
    await get_automod_config(guild_id, db_path=path)
    processed = {}
    for k, v in kwargs.items():
        if k in ("banned_words", "invite_whitelist", "whitelist_user_ids", "whitelist_role_ids") and not isinstance(v, str):
            processed[k] = json.dumps(v)
        else:
            processed[k] = v
    set_clause = ", ".join(f"{k} = ?" for k in processed.keys())
    values = list(processed.values()) + [guild_id]
    async with aiosqlite.connect(path) as db:
        await db.execute(f"UPDATE automod_config SET {set_clause} WHERE guild_id = ?", values)
        await db.commit()


# ---------- AntiRaid Config ----------

async def get_antiraid_config(guild_id: int, db_path: str = None) -> dict:
    path = _get_db_path(db_path)
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM antiraid_config WHERE guild_id = ?", (guild_id,)) as cur:
            row = await cur.fetchone()
            if row:
                return dict(row)
            await db.execute("INSERT OR IGNORE INTO antiraid_config (guild_id) VALUES (?)", (guild_id,))
            await db.commit()
        async with db.execute("SELECT * FROM antiraid_config WHERE guild_id = ?", (guild_id,)) as cur:
            row = await cur.fetchone()
            return dict(row)


async def update_antiraid_config(guild_id: int, db_path: str = None, **kwargs):
    if not kwargs:
        return
    path = _get_db_path(db_path)
    await get_antiraid_config(guild_id, db_path=path)
    set_clause = ", ".join(f"{k} = ?" for k in kwargs.keys())
    values = list(kwargs.values()) + [guild_id]
    async with aiosqlite.connect(path) as db:
        await db.execute(f"UPDATE antiraid_config SET {set_clause} WHERE guild_id = ?", values)
        await db.commit()


# ---------- AntiNuke Config ----------

async def get_antinuke_config(guild_id: int, db_path: str = None) -> dict:
    path = _get_db_path(db_path)
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM antinuke_config WHERE guild_id = ?", (guild_id,)) as cur:
            row = await cur.fetchone()
            if row:
                return dict(row)
            await db.execute("INSERT OR IGNORE INTO antinuke_config (guild_id) VALUES (?)", (guild_id,))
            await db.commit()
        async with db.execute("SELECT * FROM antinuke_config WHERE guild_id = ?", (guild_id,)) as cur:
            row = await cur.fetchone()
            return dict(row)


async def update_antinuke_config(guild_id: int, db_path: str = None, **kwargs):
    if not kwargs:
        return
    path = _get_db_path(db_path)
    await get_antinuke_config(guild_id, db_path=path)
    set_clause = ", ".join(f"{k} = ?" for k in kwargs.keys())
    values = list(kwargs.values()) + [guild_id]
    async with aiosqlite.connect(path) as db:
        await db.execute(f"UPDATE antinuke_config SET {set_clause} WHERE guild_id = ?", values)
        await db.commit()


# ---------- AntiNuke Whitelist ----------

async def is_antinuke_whitelisted(guild_id: int, target_id: int, db_path: str = None) -> bool:
    path = _get_db_path(db_path)
    async with aiosqlite.connect(path) as db:
        async with db.execute(
            "SELECT 1 FROM antinuke_whitelist WHERE guild_id = ? AND target_id = ?",
            (guild_id, target_id),
        ) as cur:
            return (await cur.fetchone()) is not None


async def add_antinuke_whitelist(guild_id: int, target_id: int, reason: str = "", added_by: int = 0, db_path: str = None):
    path = _get_db_path(db_path)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    async with aiosqlite.connect(path) as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO antinuke_whitelist (guild_id, target_id, reason, added_by, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (guild_id, target_id, reason, added_by, now),
        )
        await db.commit()


async def remove_antinuke_whitelist(guild_id: int, target_id: int, db_path: str = None) -> bool:
    path = _get_db_path(db_path)
    async with aiosqlite.connect(path) as db:
        cur = await db.execute(
            "DELETE FROM antinuke_whitelist WHERE guild_id = ? AND target_id = ?",
            (guild_id, target_id),
        )
        await db.commit()
        return cur.rowcount > 0


async def get_antinuke_whitelist(guild_id: int, db_path: str = None) -> list[dict]:
    path = _get_db_path(db_path)
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM antinuke_whitelist WHERE guild_id = ? ORDER BY id ASC",
            (guild_id,),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


# ---------- Warnings ----------

async def add_warning(guild_id: int, user_id: int, moderator_id: int, reason: str, db_path: str = None) -> int:
    path = _get_db_path(db_path)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    async with aiosqlite.connect(path) as db:
        cur = await db.execute(
            """
            INSERT INTO warnings (guild_id, user_id, moderator_id, reason, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (guild_id, user_id, moderator_id, reason, now),
        )
        await db.commit()
        return cur.lastrowid


async def get_warnings(guild_id: int, user_id: int = None, db_path: str = None) -> list[dict]:
    path = _get_db_path(db_path)
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        if user_id:
            query = "SELECT * FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY id DESC"
            params = (guild_id, user_id)
        else:
            query = "SELECT * FROM warnings WHERE guild_id = ? ORDER BY id DESC"
            params = (guild_id,)
        async with db.execute(query, params) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def delete_warning(warning_id: int, db_path: str = None) -> bool:
    path = _get_db_path(db_path)
    async with aiosqlite.connect(path) as db:
        cur = await db.execute("DELETE FROM warnings WHERE id = ?", (warning_id,))
        await db.commit()
        return cur.rowcount > 0


async def clear_warnings(guild_id: int, user_id: int, db_path: str = None) -> int:
    path = _get_db_path(db_path)
    async with aiosqlite.connect(path) as db:
        cur = await db.execute(
            "DELETE FROM warnings WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        await db.commit()
        return cur.rowcount


# ---------- Lockdown State ----------

async def save_channel_lockdown_state(
    guild_id: int, channel_id: int, existed_prior: bool, allow_bits: int, deny_bits: int, db_path: str = None
):
    path = _get_db_path(db_path)
    async with aiosqlite.connect(path) as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO lockdown_state (guild_id, channel_id, existed_prior, allow_bits, deny_bits)
            VALUES (?, ?, ?, ?, ?)
            """,
            (guild_id, channel_id, 1 if existed_prior else 0, allow_bits, deny_bits),
        )
        await db.commit()


async def get_lockdown_states(guild_id: int, db_path: str = None) -> list[dict]:
    path = _get_db_path(db_path)
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM lockdown_state WHERE guild_id = ?",
            (guild_id,),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def clear_lockdown_states(guild_id: int, db_path: str = None):
    path = _get_db_path(db_path)
    async with aiosqlite.connect(path) as db:
        await db.execute("DELETE FROM lockdown_state WHERE guild_id = ?", (guild_id,))
        await db.commit()


# ---------- Legacy Migration ----------

async def migrate_from_json(json_path: str = None, db_path: str = None) -> int:
    jpath = json_path or DEFAULT_JSON_PATH
    if not os.path.exists(jpath):
        return 0
    try:
        with open(jpath, "r") as f:
            data = json.load(f)
    except Exception:
        return 0

    if not isinstance(data, dict):
        return 0

    count = 0
    path = _get_db_path(db_path)
    async with aiosqlite.connect(path) as db:
        for guild_str, cfg in data.items():
            try:
                guild_id = int(guild_str)
            except ValueError:
                continue

            async with db.execute(
                "SELECT 1 FROM guild_config WHERE guild_id = ? AND log_channel_id IS NOT NULL", (guild_id,)
            ) as cur:
                if await cur.fetchone():
                    continue  # Already configured in SQLite, do not overwrite with legacy JSON

            await update_guild_config(
                guild_id,
                db_path=db_path,
                log_channel_id=cfg.get("log_channel_id"),
                verification_role_id=cfg.get("verification_role_id"),
                verification_channel_id=cfg.get("verification_channel_id"),
                unverified_role_id=cfg.get("unverified_role_id"),
            )

            am = cfg.get("automod", {})
            await update_automod_config(
                guild_id,
                db_path=db_path,
                enabled=1 if am.get("enabled", True) else 0,
                banned_words=am.get("banned_words", []),
                block_invites=1 if am.get("block_invites", True) else 0,
                invite_whitelist=am.get("invite_whitelist", []),
                whitelist_user_ids=cfg.get("whitelist_user_ids", []),
                whitelist_role_ids=cfg.get("whitelist_role_ids", []),
                max_mentions=am.get("max_mentions", 5),
                max_caps_percent=am.get("max_caps_percent", 70),
                spam_message_count=am.get("spam_message_count", 5),
                spam_time_window=am.get("spam_time_window", 5),
            )

            ar = cfg.get("antiraid", {})
            await update_antiraid_config(
                guild_id,
                db_path=db_path,
                enabled=1 if ar.get("enabled", True) else 0,
                join_threshold=ar.get("join_threshold", 5),
                join_time_window=ar.get("join_time_window", 10),
                min_account_age_days=ar.get("min_account_age_days", 3),
                lockdown_active=1 if ar.get("lockdown_active", False) else 0,
                action_on_raid=ar.get("action_on_raid", "kick"),
            )
            count += 1

    if count > 0 and os.path.exists(jpath):
        try:
            migrated_path = jpath + ".migrated"
            if os.path.exists(migrated_path):
                os.remove(migrated_path)
            os.rename(jpath, migrated_path)
        except OSError:
            pass

    return count

