import aiosqlite
import os
import json
import time

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "m-observe.db")


async def get_db():
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    return db


async def init_db():
    db = await get_db()
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS config (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            password_hash TEXT NOT NULL,
            api_key TEXT NOT NULL,
            telemetry_interval INTEGER DEFAULT 3,
            snapshot_interval INTEGER DEFAULT 5,
            created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS machines (
            client_id TEXT PRIMARY KEY,
            client_name TEXT NOT NULL,
            hostname TEXT,
            os TEXT,
            platform TEXT,
            ip TEXT,
            last_seen REAL,
            online INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS snapshots (
            client_id TEXT PRIMARY KEY,
            data TEXT NOT NULL,
            updated_at REAL NOT NULL,
            FOREIGN KEY (client_id) REFERENCES machines(client_id)
        );
    """)
    await db.commit()
    await db.close()


async def is_setup_done() -> bool:
    db = await get_db()
    cursor = await db.execute("SELECT COUNT(*) as cnt FROM config")
    row = await cursor.fetchone()
    await db.close()
    return row["cnt"] > 0


async def save_setup(password_hash: str, api_key: str):
    db = await get_db()
    await db.execute(
        "INSERT INTO config (id, password_hash, api_key, created_at) VALUES (1, ?, ?, ?)",
        (password_hash, api_key, time.time())
    )
    await db.commit()
    await db.close()


async def get_config() -> dict | None:
    db = await get_db()
    cursor = await db.execute("SELECT * FROM config WHERE id=1")
    row = await cursor.fetchone()
    await db.close()
    if row:
        return dict(row)
    return None


async def update_password(new_hash: str):
    db = await get_db()
    await db.execute("UPDATE config SET password_hash=? WHERE id=1", (new_hash,))
    await db.commit()
    await db.close()


async def update_api_key(new_key: str):
    db = await get_db()
    await db.execute("UPDATE config SET api_key=? WHERE id=1", (new_key,))
    await db.commit()
    await db.close()


async def update_intervals(telemetry: int, snapshot: int):
    db = await get_db()
    await db.execute(
        "UPDATE config SET telemetry_interval=?, snapshot_interval=? WHERE id=1",
        (telemetry, snapshot)
    )
    await db.commit()
    await db.close()


async def upsert_machine(client_id: str, client_name: str, hostname: str, os_str: str, platform: str, ip: str):
    db = await get_db()
    await db.execute("""
        INSERT INTO machines (client_id, client_name, hostname, os, platform, ip, last_seen, online)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1)
        ON CONFLICT(client_id) DO UPDATE SET
            client_name=excluded.client_name,
            hostname=excluded.hostname,
            os=excluded.os,
            platform=excluded.platform,
            ip=excluded.ip,
            last_seen=excluded.last_seen,
            online=1
    """, (client_id, client_name, hostname, os_str, platform, ip, time.time()))
    await db.commit()
    await db.close()


async def set_machine_offline(client_id: str):
    db = await get_db()
    await db.execute("UPDATE machines SET online=0 WHERE client_id=?", (client_id,))
    await db.commit()
    await db.close()


async def get_all_machines() -> list:
    db = await get_db()
    cursor = await db.execute("SELECT * FROM machines ORDER BY client_name")
    rows = await cursor.fetchall()
    await db.close()
    return [dict(r) for r in rows]


async def delete_machine(client_id: str):
    db = await get_db()
    await db.execute("DELETE FROM snapshots WHERE client_id=?", (client_id,))
    await db.execute("DELETE FROM machines WHERE client_id=?", (client_id,))
    await db.commit()
    await db.close()


async def upsert_snapshot(client_id: str, data: dict):
    db = await get_db()
    await db.execute("""
        INSERT INTO snapshots (client_id, data, updated_at) VALUES (?, ?, ?)
        ON CONFLICT(client_id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at
    """, (client_id, json.dumps(data), time.time()))
    await db.commit()
    await db.close()


async def get_snapshot(client_id: str) -> dict | None:
    db = await get_db()
    cursor = await db.execute("SELECT data FROM snapshots WHERE client_id=?", (client_id,))
    row = await cursor.fetchone()
    await db.close()
    if row:
        return json.loads(row["data"])
    return None
