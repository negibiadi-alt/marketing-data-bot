from __future__ import annotations
import aiosqlite
from .db import get_db


async def ensure_user(telegram_id: int, username: str | None) -> None:
    db = await get_db()
    await db.execute(
        """
        INSERT INTO users (telegram_id, username)
        VALUES (?, ?)
        ON CONFLICT(telegram_id) DO UPDATE SET username = excluded.username
        """,
        (telegram_id, username),
    )
    await db.commit()


async def get_or_create_partner(tag: str, created_by: int) -> int:
    """Returns partner id. tag is stored lowercase without #."""
    tag = tag.lower().lstrip("#")
    db = await get_db()
    row = await (await db.execute("SELECT id FROM partners WHERE tag = ?", (tag,))).fetchone()
    if row:
        return row["id"]
    cur = await db.execute(
        "INSERT INTO partners (tag, created_by) VALUES (?, ?)", (tag, created_by)
    )
    await db.commit()
    return cur.lastrowid


async def add_entry(
    partner_id: int,
    user_id: int,
    entry_type: str,
    title: str | None = None,
    description: str | None = None,
    link: str | None = None,
    file_path: str | None = None,
    file_id: str | None = None,
    tags: str | None = None,
) -> int:
    db = await get_db()
    cur = await db.execute(
        """
        INSERT INTO entries
            (partner_id, user_id, entry_type, title, description, link, file_path, file_id, tags)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (partner_id, user_id, entry_type, title, description, link, file_path, file_id, tags),
    )
    await db.commit()
    return cur.lastrowid


async def get_partner_by_tag(tag: str) -> aiosqlite.Row | None:
    tag = tag.lower().lstrip("#")
    db = await get_db()
    return await (
        await db.execute("SELECT * FROM partners WHERE tag = ?", (tag,))
    ).fetchone()


async def get_partner_entries(tag: str) -> tuple[aiosqlite.Row | None, list[aiosqlite.Row]]:
    """Returns (partner_row, list_of_entries_with_username)."""
    tag = tag.lower().lstrip("#")
    db = await get_db()
    partner = await (
        await db.execute("SELECT * FROM partners WHERE tag = ?", (tag,))
    ).fetchone()
    if not partner:
        return None, []
    entries = await (
        await db.execute(
            """
            SELECT e.*, u.username
            FROM entries e
            LEFT JOIN users u ON e.user_id = u.telegram_id
            WHERE e.partner_id = ?
            ORDER BY e.created_at DESC
            """,
            (partner["id"],),
        )
    ).fetchall()
    return partner, entries


async def find_by_link(url: str) -> aiosqlite.Row | None:
    db = await get_db()
    return await (
        await db.execute(
            """
            SELECT e.*, p.tag, u.username
            FROM entries e
            JOIN partners p ON e.partner_id = p.id
            LEFT JOIN users u ON e.user_id = u.telegram_id
            WHERE e.link = ?
            LIMIT 1
            """,
            (url,),
        )
    ).fetchone()


async def search_entries(keyword: str) -> list[aiosqlite.Row]:
    db = await get_db()
    kw = f"%{keyword}%"
    return await (
        await db.execute(
            """
            SELECT e.*, p.tag, u.username
            FROM entries e
            JOIN partners p ON e.partner_id = p.id
            LEFT JOIN users u ON e.user_id = u.telegram_id
            WHERE e.description LIKE ? OR e.title LIKE ? OR e.link LIKE ?
            ORDER BY e.created_at DESC
            LIMIT 50
            """,
            (kw, kw, kw),
        )
    ).fetchall()


async def get_recent(limit: int = 10) -> list[aiosqlite.Row]:
    db = await get_db()
    return await (
        await db.execute(
            """
            SELECT e.*, p.tag, u.username
            FROM entries e
            JOIN partners p ON e.partner_id = p.id
            LEFT JOIN users u ON e.user_id = u.telegram_id
            ORDER BY e.created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
    ).fetchall()


async def get_stats() -> dict:
    db = await get_db()
    partner_count = (
        await (await db.execute("SELECT COUNT(*) as c FROM partners")).fetchone()
    )["c"]
    entry_count = (
        await (await db.execute("SELECT COUNT(*) as c FROM entries")).fetchone()
    )["c"]
    top_partners = await (
        await db.execute(
            """
            SELECT p.tag, COUNT(e.id) as cnt
            FROM partners p
            LEFT JOIN entries e ON p.id = e.partner_id
            GROUP BY p.id
            ORDER BY cnt DESC
            LIMIT 5
            """
        )
    ).fetchall()
    return {
        "partner_count": partner_count,
        "entry_count": entry_count,
        "top_partners": top_partners,
    }


async def get_all_partners() -> list[aiosqlite.Row]:
    db = await get_db()
    return await (
        await db.execute(
            """
            SELECT p.*, COUNT(e.id) as entry_count,
                   MAX(e.created_at) as last_entry
            FROM partners p
            LEFT JOIN entries e ON p.id = e.partner_id
            GROUP BY p.id
            ORDER BY last_entry DESC NULLS LAST
            """
        )
    ).fetchall()


async def delete_partner(tag: str) -> bool:
    tag = tag.lower().lstrip("#")
    db = await get_db()
    cur = await db.execute("DELETE FROM partners WHERE tag = ?", (tag,))
    await db.commit()
    return cur.rowcount > 0


async def get_partner_photos(partner_id: int) -> list[aiosqlite.Row]:
    db = await get_db()
    return await (
        await db.execute(
            "SELECT * FROM entries WHERE partner_id = ? AND entry_type = 'photo'",
            (partner_id,),
        )
    ).fetchall()


async def get_partner_links(partner_id: int) -> list[aiosqlite.Row]:
    db = await get_db()
    return await (
        await db.execute(
            """
            SELECT e.*, u.username
            FROM entries e
            LEFT JOIN users u ON e.user_id = u.telegram_id
            WHERE e.partner_id = ? AND e.link IS NOT NULL
            ORDER BY e.created_at DESC
            """,
            (partner_id,),
        )
    ).fetchall()


async def get_db_summary() -> str:
    """Returns a text summary of the database for the AI system prompt."""
    stats = await get_stats()
    partners = await get_all_partners()
    lines = [
        f"Toplam partner: {stats['partner_count']}",
        f"Toplam kayıt: {stats['entry_count']}",
        "",
        "Partnerler:",
    ]
    for p in partners:
        last = p["last_entry"] or "henüz kayıt yok"
        lines.append(f"  #{p['tag']} — {p['entry_count']} kayıt, son: {last}")
    return "\n".join(lines)
