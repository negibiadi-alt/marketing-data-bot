from __future__ import annotations
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from config import ADMIN_IDS
from database import queries as q
from utils.parser import extract_hashtags, extract_urls, normalize_tag
from utils.formatter import (
    format_partner_list, format_stats, format_recent, format_search_results
)

logger = logging.getLogger(__name__)


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await q.ensure_user(user.id, user.username)
    await update.message.reply_html(
        f"👋 Merhaba <b>@{user.username or user.first_name}</b>!\n\n"
        "Ben Marketing Data Bot'um. Partner verilerini yönetmenize yardımcı olurum.\n\n"
        "<b>Temel kullanım:</b>\n"
        "• <code>/add #partner https://link açıklama</code>\n"
        "• <code>#partner</code> yazarak verileri sorgula\n"
        "• Bir link yazarak kayıtlı mı kontrol et\n"
        "• Fotoğraf + caption ile ekran görüntüsü kaydet\n"
        "• Doğal soru sor, AI yanıtlasın\n\n"
        "<code>/help</code> ile tüm komutları gör."
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await q.ensure_user(update.effective_user.id, update.effective_user.username)
    text = (
        "📖 <b>Komut Listesi</b>\n\n"
        "<b>Veri Ekleme</b>\n"
        "• <code>/add #partner https://link açıklama</code> — Veri ekle\n"
        "• <code>/note #partner not metni</code> — Sadece not ekle\n\n"
        "<b>Sorgulama</b>\n"
        "• <code>#partner</code> — Partner verilerini gör\n"
        "• <code>https://...</code> — Link kayıtlı mı kontrol et\n"
        "• <code>/partners</code> — Tüm partnerler\n"
        "• <code>/recent [sayı]</code> — Son kayıtlar (default: 10)\n"
        "• <code>/search kelime</code> — Arama\n"
        "• <code>/stats</code> — İstatistikler\n\n"
        "<b>Dışa Aktarma</b>\n"
        "• <code>/export #partner</code> — Partner verilerini dışa aktar\n\n"
        "<b>Admin</b>\n"
        "• <code>/delete #partner</code> — Partner sil\n\n"
        "<b>AI Sohbet</b>\n"
        "• Herhangi bir soru yaz → Claude AI yanıtlar\n"
        "• 'en çok veri hangi partnerde?', 'bu hafta ne ekledik?' gibi"
    )
    await update.message.reply_html(text)


async def cmd_add(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await q.ensure_user(user.id, user.username)

    args_text = " ".join(ctx.args) if ctx.args else ""
    if not args_text:
        await update.message.reply_html(
            "❌ Kullanım: <code>/add #partner https://link açıklama</code>"
        )
        return

    tags = extract_hashtags(args_text)
    urls = extract_urls(args_text)

    if not tags:
        await update.message.reply_html(
            "❌ En az bir <code>#partner</code> etiketi gerekli."
        )
        return

    # Remove tags and URLs from text to get description
    import re
    desc = re.sub(r"#\w+", "", args_text)
    desc = re.sub(r"https?://\S+", "", desc).strip()

    tag = tags[0]
    link = urls[0] if urls else None
    entry_type = "link" if link else "data"

    partner_id = await q.get_or_create_partner(tag, user.id)
    await q.add_entry(
        partner_id=partner_id,
        user_id=user.id,
        entry_type=entry_type,
        description=desc or None,
        link=link,
    )

    msg = f"✅ <b>#{tag}</b> için kayıt eklendi."
    if link:
        msg += f"\n🔗 {link}"
    if desc:
        msg += f"\n📝 {desc}"
    await update.message.reply_html(msg)


async def cmd_note(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await q.ensure_user(user.id, user.username)

    args_text = " ".join(ctx.args) if ctx.args else ""
    tags = extract_hashtags(args_text)
    if not tags:
        await update.message.reply_html(
            "❌ Kullanım: <code>/note #partner not metni</code>"
        )
        return

    import re
    note_text = re.sub(r"#\w+", "", args_text).strip()
    tag = tags[0]
    partner_id = await q.get_or_create_partner(tag, user.id)
    await q.add_entry(
        partner_id=partner_id,
        user_id=user.id,
        entry_type="note",
        description=note_text or None,
    )
    await update.message.reply_html(
        f"📝 <b>#{tag}</b> için not eklendi."
        + (f"\n{note_text}" if note_text else "")
    )


async def cmd_partners(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await q.ensure_user(update.effective_user.id, update.effective_user.username)
    partners = await q.get_all_partners()
    if not partners:
        await update.message.reply_html(
            "Henüz hiç partner yok. <code>/add #partner</code> ile ekleyin."
        )
        return

    from utils.formatter import relative_time
    lines = ["📁 <b>Tüm Partnerler</b>\n"]
    keyboard = []
    for p in partners:
        last = relative_time(p["last_entry"]) if p["last_entry"] else "kayıt yok"
        lines.append(f"• <b>#{p['tag']}</b> — {p['entry_count']} kayıt, {last}")
        keyboard.append([InlineKeyboardButton(f"#{p['tag']}", callback_data=f"partner:{p['tag']}")])

    await update.message.reply_html(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await q.ensure_user(update.effective_user.id, update.effective_user.username)
    stats = await q.get_stats()
    await update.message.reply_html(format_stats(stats))


async def cmd_recent(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await q.ensure_user(update.effective_user.id, update.effective_user.username)
    limit = 10
    if ctx.args:
        try:
            limit = int(ctx.args[0])
            limit = max(1, min(50, limit))
        except ValueError:
            pass
    entries = await q.get_recent(limit)
    await update.message.reply_html(format_recent(entries), disable_web_page_preview=True)


async def cmd_search(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await q.ensure_user(update.effective_user.id, update.effective_user.username)
    keyword = " ".join(ctx.args) if ctx.args else ""
    if not keyword:
        await update.message.reply_html("❌ Kullanım: <code>/search kelime</code>")
        return
    entries = await q.search_entries(keyword)
    await update.message.reply_html(
        format_search_results(entries, keyword), disable_web_page_preview=True
    )


async def cmd_delete(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await q.ensure_user(user.id, user.username)
    if user.id not in ADMIN_IDS:
        await update.message.reply_html("⛔ Bu komut sadece adminler içindir.")
        return

    args_text = " ".join(ctx.args) if ctx.args else ""
    tags = extract_hashtags(args_text) or ([normalize_tag(args_text)] if args_text else [])
    if not tags:
        await update.message.reply_html("❌ Kullanım: <code>/delete #partner</code>")
        return

    tag = tags[0]
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Evet, sil", callback_data=f"confirm_delete:{tag}"),
        InlineKeyboardButton("❌ İptal", callback_data="cancel"),
    ]])
    await update.message.reply_html(
        f"⚠️ <b>#{tag}</b> ve tüm verilerini silmek istediğinize emin misiniz?",
        reply_markup=keyboard,
    )


async def cmd_export(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await q.ensure_user(update.effective_user.id, update.effective_user.username)
    args_text = " ".join(ctx.args) if ctx.args else ""
    tags = extract_hashtags(args_text) or ([normalize_tag(args_text)] if args_text else [])
    if not tags:
        await update.message.reply_html("❌ Kullanım: <code>/export #partner</code>")
        return

    tag = tags[0]
    partner, entries = await q.get_partner_entries(tag)
    if not partner:
        await update.message.reply_html(f"❌ <b>#{tag}</b> bulunamadı.")
        return

    lines = [f"# #{tag} — {len(entries)} kayıt\n"]
    for e in entries:
        username = e["username"] or "anonim"
        lines.append(
            f"[{e['created_at']}] @{username} ({e['entry_type']})"
        )
        if e["title"]:
            lines.append(f"  Başlık: {e['title']}")
        if e["description"]:
            lines.append(f"  Açıklama: {e['description']}")
        if e["link"]:
            lines.append(f"  Link: {e['link']}")
        lines.append("")

    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n\n... (kısaltıldı)"
    await update.message.reply_text(f"📋 #{tag} Dışa Aktarma:\n\n{text}")
