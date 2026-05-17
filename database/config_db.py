import os
from pathlib import Path

import aiosqlite


DATABASE_URL = os.getenv("DATABASE_URL")
DB_PATH = os.getenv("DATABASE_PATH") or os.getenv("DB_PATH") or "config.db"
_pg_pool = None


def use_postgres() -> bool:
    return bool(DATABASE_URL and DATABASE_URL.startswith(("postgres://", "postgresql://")))


async def get_pg_pool():
    global _pg_pool
    if _pg_pool is None:
        import asyncpg

        _pg_pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    return _pg_pool


async def db_init():
    if use_postgres():
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS config (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
                """
            )
        print("[database] using PostgreSQL DATABASE_URL", flush=True)
        return

    db_dir = Path(DB_PATH).parent
    if str(db_dir) not in ("", "."):
        db_dir.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        await db.commit()
    print(f"[database] using SQLite {DB_PATH}", flush=True)


async def db_set(key: str, value: str):
    if use_postgres():
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO config (key, value)
                VALUES ($1, $2)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                """,
                key,
                value,
            )
        return

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "REPLACE INTO config (key, value) VALUES (?, ?)",
            (key, value),
        )
        await db.commit()


async def db_get(key: str):
    if use_postgres():
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            return await conn.fetchval("SELECT value FROM config WHERE key = $1", key)

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT value FROM config WHERE key = ?",
            (key,),
        )
        row = await cursor.fetchone()
        return row[0] if row else None


async def db_get_all_config():
    if use_postgres():
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT key, value FROM config")
            return {row["key"]: row["value"] for row in rows}

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT key, value FROM config")
        rows = await cursor.fetchall()
        return {key: value for key, value in rows}
