import os
from pathlib import Path

import aiosqlite


DB_PATH = os.getenv("DATABASE_PATH") or os.getenv("DB_PATH") or "config.db"


async def db_init():
    db_dir = Path(DB_PATH).parent
    if str(db_dir) not in ("", "."):
        db_dir.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await db.commit()


async def db_set(key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "REPLACE INTO config (key, value) VALUES (?, ?)",
            (key, value),
        )
        await db.commit()


async def db_get(key: str):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT value FROM config WHERE key = ?",
            (key,),
        )
        row = await cursor.fetchone()
        return row[0] if row else None


async def db_get_all_config():
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT key, value FROM config")
        rows = await cursor.fetchall()
        return {key: value for key, value in rows}
