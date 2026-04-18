import aiosqlite
import logging
from .models import SCHEMA_SQL

logger = logging.getLogger(__name__)

DB_PATH = "marketing.db"
_db: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        _db = await aiosqlite.connect(DB_PATH)
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA foreign_keys = ON")
        await _db.commit()
        logger.info("Database connection established: %s", DB_PATH)
    return _db


async def init_db() -> None:
    db = await get_db()
    await db.executescript(SCHEMA_SQL)
    await db.commit()
    logger.info("Database schema initialized")


async def close_db() -> None:
    global _db
    if _db is not None:
        await _db.close()
        _db = None
        logger.info("Database connection closed")
