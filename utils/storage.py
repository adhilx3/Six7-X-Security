"""
Lightweight JSON-backed storage for per-guild configuration.
Not meant for huge scale, but perfectly fine for a single-server-to-mid-size security bot.
For larger deployments, swap this out for SQLite/PostgreSQL.
"""

import json
import os
import threading

DATA_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "guild_config.json")

_lock = threading.Lock()

DEFAULT_CONFIG = {
    "log_channel_id": None,
    "verification_role_id": None,
    "verification_channel_id": None,
    "unverified_role_id": None,
    "muted_role_id": None,
    "automod": {
        "enabled": True,
        "banned_words": [],
        "block_invites": True,
        "invite_whitelist": [],
        "max_mentions": 5,
        "max_caps_percent": 70,
        "spam_message_count": 5,
        "spam_time_window": 5,
    },
    "antiraid": {
        "enabled": True,
        "join_threshold": 5,
        "join_time_window": 10,
        "min_account_age_days": 3,
        "lockdown_active": False,
        "action_on_raid": "kick",
    },
    "whitelist_user_ids": [],
    "whitelist_role_ids": [],
}


def _ensure_file():
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w") as f:
            json.dump({}, f)


def _load_all():
    _ensure_file()
    with open(DATA_FILE, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def _save_all(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_guild_config(guild_id: int) -> dict:
    with _lock:
        data = _load_all()
        key = str(guild_id)
        if key not in data:
            data[key] = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
            _save_all(data)
        else:
            # backfill any new default keys added after the config was first created
            merged = json.loads(json.dumps(DEFAULT_CONFIG))
            merged.update(data[key])
            for section in ("automod", "antiraid"):
                merged_section = json.loads(json.dumps(DEFAULT_CONFIG[section]))
                merged_section.update(data[key].get(section, {}))
                merged[section] = merged_section
            data[key] = merged
        return data[key]


def save_guild_config(guild_id: int, config: dict):
    with _lock:
        data = _load_all()
        data[str(guild_id)] = config
        _save_all(data)


def update_guild_config(guild_id: int, updater):
    """updater: function(config_dict) -> None, mutates config in place then saves."""
    with _lock:
        data = _load_all()
        key = str(guild_id)
        if key not in data:
            data[key] = json.loads(json.dumps(DEFAULT_CONFIG))
        updater(data[key])
        _save_all(data)
