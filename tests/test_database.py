import os
import json
import pytest
import aiosqlite

from utils.database import (
    init_db,
    get_guild_config,
    update_guild_config,
    get_automod_config,
    update_automod_config,
    get_antiraid_config,
    update_antiraid_config,
    get_antinuke_config,
    update_antinuke_config,
    is_antinuke_whitelisted,
    add_antinuke_whitelist,
    remove_antinuke_whitelist,
    get_antinuke_whitelist,
    add_warning,
    get_warnings,
    delete_warning,
    clear_warnings,
    save_channel_lockdown_state,
    get_lockdown_states,
    clear_lockdown_states,
    migrate_from_json,
)


@pytest.fixture
async def temp_db(tmp_path):
    db_file = str(tmp_path / "test_security.db")
    await init_db(db_file)
    yield db_file


@pytest.mark.asyncio
async def test_guild_config_defaults_and_updates(temp_db):
    guild_id = 12345
    cfg = await get_guild_config(guild_id, db_path=temp_db)
    assert cfg["guild_id"] == guild_id
    assert cfg["verification_type"] == "button"
    assert cfg["log_channel_id"] is None

    await update_guild_config(guild_id, log_channel_id=9999, verification_type="captcha", db_path=temp_db)
    updated = await get_guild_config(guild_id, db_path=temp_db)
    assert updated["log_channel_id"] == 9999
    assert updated["verification_type"] == "captcha"


@pytest.mark.asyncio
async def test_automod_config(temp_db):
    guild_id = 12345
    cfg = await get_automod_config(guild_id, db_path=temp_db)
    assert cfg["enabled"] == 1
    assert cfg["banned_words"] == []
    assert cfg["block_scams"] == 1

    await update_automod_config(
        guild_id,
        banned_words=["scam", "hack"],
        max_mentions=3,
        db_path=temp_db,
    )
    updated = await get_automod_config(guild_id, db_path=temp_db)
    assert updated["banned_words"] == ["scam", "hack"]
    assert updated["max_mentions"] == 3


@pytest.mark.asyncio
async def test_antiraid_config(temp_db):
    guild_id = 12345
    cfg = await get_antiraid_config(guild_id, db_path=temp_db)
    assert cfg["enabled"] == 1
    assert cfg["action_on_raid"] == "kick"
    assert cfg["lockdown_active"] == 0

    await update_antiraid_config(guild_id, lockdown_active=1, original_verification_level="low", db_path=temp_db)
    updated = await get_antiraid_config(guild_id, db_path=temp_db)
    assert updated["lockdown_active"] == 1
    assert updated["original_verification_level"] == "low"


@pytest.mark.asyncio
async def test_antinuke_config_and_whitelist(temp_db):
    guild_id = 12345
    cfg = await get_antinuke_config(guild_id, db_path=temp_db)
    assert cfg["enabled"] == 1
    assert cfg["punishment"] == "strip_roles"

    await update_antinuke_config(guild_id, punishment="ban", max_channel_actions=5, db_path=temp_db)
    updated = await get_antinuke_config(guild_id, db_path=temp_db)
    assert updated["punishment"] == "ban"
    assert updated["max_channel_actions"] == 5

    assert not await is_antinuke_whitelisted(guild_id, 9876, db_path=temp_db)
    await add_antinuke_whitelist(guild_id, 9876, reason="Co-owner", added_by=1111, db_path=temp_db)
    assert await is_antinuke_whitelisted(guild_id, 9876, db_path=temp_db)

    wl = await get_antinuke_whitelist(guild_id, db_path=temp_db)
    assert len(wl) == 1
    assert wl[0]["target_id"] == 9876
    assert wl[0]["reason"] == "Co-owner"

    removed = await remove_antinuke_whitelist(guild_id, 9876, db_path=temp_db)
    assert removed is True
    assert not await is_antinuke_whitelisted(guild_id, 9876, db_path=temp_db)


@pytest.mark.asyncio
async def test_warnings_crud(temp_db):
    guild_id = 12345
    user_id = 55555
    mod_id = 99999

    warn_id_1 = await add_warning(guild_id, user_id, mod_id, "Rule 1 broken", db_path=temp_db)
    warn_id_2 = await add_warning(guild_id, user_id, mod_id, "Rule 2 broken", db_path=temp_db)
    assert warn_id_1 > 0
    assert warn_id_2 > warn_id_1

    warns = await get_warnings(guild_id, user_id, db_path=temp_db)
    assert len(warns) == 2
    assert warns[0]["reason"] == "Rule 2 broken"
    assert warns[1]["reason"] == "Rule 1 broken"

    deleted = await delete_warning(warn_id_1, db_path=temp_db)
    assert deleted is True

    warns_after = await get_warnings(guild_id, user_id, db_path=temp_db)
    assert len(warns_after) == 1
    assert warns_after[0]["id"] == warn_id_2

    cleared_count = await clear_warnings(guild_id, user_id, db_path=temp_db)
    assert cleared_count == 1
    assert len(await get_warnings(guild_id, user_id, db_path=temp_db)) == 0


@pytest.mark.asyncio
async def test_lockdown_state(temp_db):
    guild_id = 12345
    channel_id = 88888
    await save_channel_lockdown_state(
        guild_id, channel_id, existed_prior=True, allow_bits=1024, deny_bits=2048, db_path=temp_db
    )
    states = await get_lockdown_states(guild_id, db_path=temp_db)
    assert len(states) == 1
    assert states[0]["channel_id"] == channel_id
    assert states[0]["existed_prior"] == 1
    assert states[0]["allow_bits"] == 1024
    assert states[0]["deny_bits"] == 2048

    await clear_lockdown_states(guild_id, db_path=temp_db)
    assert len(await get_lockdown_states(guild_id, db_path=temp_db)) == 0


@pytest.mark.asyncio
async def test_legacy_json_migration(tmp_path):
    json_path = tmp_path / "legacy_config.json"
    db_file = str(tmp_path / "migrated.db")
    legacy_data = {
        "77777": {
            "log_channel_id": 111,
            "verification_role_id": 222,
            "automod": {
                "enabled": True,
                "banned_words": ["badword"],
                "block_invites": True,
                "max_mentions": 4,
            },
            "antiraid": {
                "enabled": True,
                "join_threshold": 6,
                "min_account_age_days": 5,
            },
            "whitelist_user_ids": [333],
            "whitelist_role_ids": [444],
        }
    }
    with open(json_path, "w") as f:
        json.dump(legacy_data, f)

    await init_db(db_file)
    migrated_count = await migrate_from_json(str(json_path), db_path=db_file)
    assert migrated_count == 1

    cfg = await get_guild_config(77777, db_path=db_file)
    assert cfg["log_channel_id"] == 111
    assert cfg["verification_role_id"] == 222

    am = await get_automod_config(77777, db_path=db_file)
    assert am["banned_words"] == ["badword"]
    assert am["max_mentions"] == 4
    assert am["whitelist_user_ids"] == [333]
    assert am["whitelist_role_ids"] == [444]

    ar = await get_antiraid_config(77777, db_path=db_file)
    assert ar["join_threshold"] == 6
    assert ar["min_account_age_days"] == 5
