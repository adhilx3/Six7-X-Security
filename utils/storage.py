"""
[DEPRECATED] Legacy JSON storage.
All bot storage has been upgraded to async SQLite in utils.database.
This file is kept for backwards compatibility with any existing external scripts.
"""

from utils.database import (
    DEFAULT_DB_PATH,
    DEFAULT_JSON_PATH,
    init_db,
    migrate_from_json,
)
