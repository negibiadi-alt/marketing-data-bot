from __future__ import annotations
from datetime import datetime, timezone
import aiosqlite


def relative_time(dt_str: str) -> str:
    """Convert a SQLite datetime string to a human-readable relative time."""
    try:
        dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        now = datetime.now()
        diff = now - dt
        seconds = int(diff.total_seconds())
        if seconds < 60:
            return "az önce"
        elif seconds < 3600:
            return f"{seconds // 60} dakika önce"
        elif seconds < 86400:
            return f"{seconds // 3600} saat önce"
        elif seconds < 604800:
            return f"{diff.days} gün önce"
        elif seconds < 2592000:
            return f"{diff.days // 7} hafta önce"
        else:
            return dt.strftime("%d.%m.%Y")
    except Exception:
        return dt_str or "bilinmiyor"


def format_entry(entry: aiosqlite.Row) -> str:
    """Format a single entry row as a Telegram message line."""
    username = entry["username"] or "anonim"
    time_str = relative_time(entry["created_at"])
    icon = {
        "link": "🔗",
        "photo": "📸",
        "note": "📝",
        "data": "📊",
    }.get(entry["entry_type"], "•")

    parts = [f"{icon} <b>@{username}</b> — {time_str}"]
    if entry["title"]:
        parts.append(f"  <i>{entry['title']}</i>")
    if entry["description"]:
        parts.append(f"  {entry['description']}")
    if entry["link"]:
        parts.append(f"  🔗 {entry['link']}")
    return "\n".join(parts)


def format_partner_list(partner: aiosqlite.Row, entries: list[aiosqlite.Row]) -> str:
    tag = partner["tag"]
    total = len(entries)
    header = f"📁 <b>#{tag}</b> — {total} kayıt\n{'─' * 30}\n"

    if not entries:
        return header + "Henüz kayıt yok."

    body_parts = []
    for entry in entries[:20]:  # Show latest 20
        body_parts.append(format_entry(entry))

    body = "\n\n".join(body_parts)
    footer = f"\n\n<i>Toplam {total} kayıt</i>" if total > 20 else ""
    return header + body + footer


def format_stats(stats: dict) -> str:
    lines = [
        "📊 <b>Genel İstatistikler</b>",
        f"├ Partner sayısı: <b>{stats['partner_count']}</b>",
        f"└ Toplam kayıt: <b>{stats['entry_count']}</b>",
        "",
        "🏆 <b>En Aktif Partnerler</b>",
    ]
    for p in stats["top_partners"]:
        lines.append(f"  #{p['tag']} — {p['cnt']} kayıt")
    return "\n".join(lines)


def format_recent(entries: list[aiosqlite.Row]) -> str:
    if not entries:
        return "Henüz hiç kayıt yok."
    lines = ["🕐 <b>Son Kayıtlar</b>\n"]
    for entry in entries:
        tag = entry["tag"] if "tag" in entry.keys() else "?"
        lines.append(f"<b>#{tag}</b> — {format_entry(entry)}")
    return "\n\n".join(lines)


def format_search_results(entries: list[aiosqlite.Row], keyword: str) -> str:
    if not entries:
        return f"🔍 '<b>{keyword}</b>' için sonuç bulunamadı."
    lines = [f"🔍 <b>'{keyword}'</b> — {len(entries)} sonuç\n"]
    for entry in entries:
        tag = entry["tag"] if "tag" in entry.keys() else "?"
        lines.append(f"<b>#{tag}</b> — {format_entry(entry)}")
    return "\n\n".join(lines)
