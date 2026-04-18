from __future__ import annotations
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from database import queries as q
from utils.parser import is_only_hashtag, is_only_url, extract_urls
from utils.formatter import format_partner_list, relative_time
from ai.claude import ai

logger = logging.getLogger(__name__)

# user_id -> pending save data (when partner not detected)
# { "links": [...], "description": "...", "original_text": "..." }
_pending_saves: dict[int, dict] = {}


def _partner_keyboard(partner_id: int, tag: str, is_admin: bool) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("📸 Fotoğraflar", callback_data=f"send_photos:{partner_id}"),
            InlineKeyboardButton("📋 Linkler", callback_data=f"list_links:{partner_id}"),
        ],
        [
            InlineKeyboardButton("🤖 AI Özeti", callback_data=f"ai_summary:{tag}"),
        ],
    ]
    if is_admin:
        rows.append([
            InlineKeyboardButton("🗑 Sil (Admin)", callback_data=f"confirm_delete:{tag}"),
        ])
    return InlineKeyboardMarkup(rows)


async def _save_entries(partner_tag: str, user_id: int, links: list[str], description: str | None) -> str:
    """Save one or more entries to DB and return confirmation message."""
    partner_id = await q.get_or_create_partner(partner_tag, user_id)
    saved = []

    if links:
        for link in links:
            await q.add_entry(
                partner_id=partner_id,
                user_id=user_id,
                entry_type="link",
                description=description,
                link=link,
            )
            saved.append(f"🔗 {link}")

    if description and not links:
        await q.add_entry(
            partner_id=partner_id,
            user_id=user_id,
            entry_type="note",
            description=description,
        )
        saved.append(f"📝 {description}")
    elif description and links:
        # Description already attached to link entries above
        pass

    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    items = "\n".join(saved)
    return (
        f"✅ <b>#{partner_tag}</b> için kaydettim ({now}):\n{items}"
        if saved else
        f"✅ <b>#{partner_tag}</b> için not kaydettim ({now})"
    )


async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    text = update.message.text or ""
    await q.ensure_user(user.id, user.username)

    from config import ADMIN_IDS

    # ── Fast path: bare #hashtag → partner query ──────────
    tag = is_only_hashtag(text)
    if tag:
        partner, entries = await q.get_partner_entries(tag)
        if not partner:
            await update.message.reply_html(
                f"❓ <b>#{tag}</b> kayıtlı değil.\n"
                f"Eklemek için bilgiyi yaz, ben kaydederim — ya da:\n"
                f"<code>/add #{tag} https://link açıklama</code>"
            )
            return
        msg = format_partner_list(partner, entries)
        keyboard = _partner_keyboard(partner["id"], tag, user.id in ADMIN_IDS)
        await update.message.reply_html(msg, reply_markup=keyboard, disable_web_page_preview=True)
        return

    # ── Fast path: bare URL → duplicate check ─────────────
    url = is_only_url(text)
    if url:
        row = await q.find_by_link(url)
        if row:
            username = row["username"] or "anonim"
            time_str = relative_time(row["created_at"])
            await update.message.reply_html(
                f"✅ Bu link kayıtlı!\n"
                f"👤 @{username} — {time_str}\n"
                f"📁 <b>#{row['tag']}</b> altında"
            )
        else:
            await update.message.reply_html(
                f"❌ Bu link kayıtlı değil.\n"
                f"Hangi partner için? Şöyle yaz:\n"
                f"<i>bigbangers için {url}</i>"
            )
        return

    # ── AI intent detection ────────────────────────────────
    await update.message.chat.send_action("typing")
    intent = await ai.classify(text)

    logger.info(
        "Intent for user %s: %s | partner=%s | links=%s",
        user.id, intent.type, intent.partner, intent.links,
    )

    # ── SAVE intent ────────────────────────────────────────
    if intent.type == "SAVE":
        if intent.partner:
            # Partner detected → save immediately
            confirm = await _save_entries(intent.partner, user.id, intent.links, intent.description)
            await update.message.reply_html(confirm, disable_web_page_preview=True)
        else:
            # Partner not detected → ask user
            _pending_saves[user.id] = {
                "links": intent.links,
                "description": intent.description,
                "original_text": text,
            }
            partners = await q.get_all_partners()
            keyboard_rows = []
            for p in partners[:8]:
                keyboard_rows.append([
                    InlineKeyboardButton(f"#{p['tag']}", callback_data=f"save_to:{p['tag']}")
                ])
            keyboard_rows.append([
                InlineKeyboardButton("✏️ Yeni partner adı gir", callback_data="save_new_partner"),
                InlineKeyboardButton("❌ İptal", callback_data="cancel_save"),
            ])
            await update.message.reply_html(
                "💾 Bunu kaydetmek istiyorum — hangi partner için?\n\n"
                + (f"🔗 {', '.join(intent.links)}\n" if intent.links else "")
                + (f"📝 {intent.description}\n" if intent.description else ""),
                reply_markup=InlineKeyboardMarkup(keyboard_rows),
            )
        return

    # ── QUERY / CHAT intent → Gemini with DB context ───────
    reply = await ai.chat(user.id, user.username, text)
    await update.message.reply_html(reply, disable_web_page_preview=True)


async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    user = update.effective_user
    from config import ADMIN_IDS

    # ── Pending save: user picked a partner ───────────────
    if data.startswith("save_to:"):
        tag = data.split(":", 1)[1]
        pending = _pending_saves.pop(user.id, None)
        if not pending:
            await query.edit_message_text("❌ Bekleyen kayıt bulunamadı.")
            return
        confirm = await _save_entries(tag, user.id, pending["links"], pending["description"])
        await query.edit_message_text(confirm, parse_mode=ParseMode.HTML)
        return

    if data == "save_new_partner":
        pending = _pending_saves.get(user.id)
        if not pending:
            await query.edit_message_text("❌ Bekleyen kayıt bulunamadı.")
            return
        await query.edit_message_text(
            "✏️ Partner adını yaz (örn: <code>bigbangers</code>):",
            parse_mode=ParseMode.HTML,
        )
        ctx.user_data["awaiting_partner_name"] = True
        return

    if data == "cancel_save":
        _pending_saves.pop(user.id, None)
        await query.edit_message_text("❌ İptal edildi.")
        return

    # ── Partner detail view ───────────────────────────────
    if data.startswith("partner:"):
        tag = data.split(":", 1)[1]
        partner, entries = await q.get_partner_entries(tag)
        if not partner:
            await query.edit_message_text(f"❌ #{tag} bulunamadı.")
            return
        msg = format_partner_list(partner, entries)
        keyboard = _partner_keyboard(partner["id"], tag, user.id in ADMIN_IDS)
        await query.edit_message_text(msg, parse_mode=ParseMode.HTML, reply_markup=keyboard)

    elif data.startswith("send_photos:"):
        partner_id = int(data.split(":", 1)[1])
        photos = await q.get_partner_photos(partner_id)
        if not photos:
            await query.message.reply_text("Bu partner için kayıtlı fotoğraf yok.")
            return
        for photo in photos:
            try:
                if photo["file_id"]:
                    await query.message.reply_photo(photo["file_id"])
                elif photo["file_path"]:
                    with open(photo["file_path"], "rb") as f:
                        await query.message.reply_photo(f)
            except Exception as e:
                logger.warning("Could not send photo %s: %s", photo["id"], e)

    elif data.startswith("list_links:"):
        partner_id = int(data.split(":", 1)[1])
        links = await q.get_partner_links(partner_id)
        if not links:
            await query.message.reply_text("Bu partner için kayıtlı link yok.")
            return
        lines = ["🔗 <b>Kayıtlı Linkler</b>\n"]
        for row in links:
            username = row["username"] or "anonim"
            time_str = relative_time(row["created_at"])
            lines.append(f"• {row['link']}\n  @{username} — {time_str}")
        await query.message.reply_html("\n".join(lines), disable_web_page_preview=True)

    elif data.startswith("ai_summary:"):
        tag = data.split(":", 1)[1]
        await query.message.chat.send_action("typing")
        summary = await ai.summarize_partner(tag)
        await query.message.reply_html(summary)

    elif data.startswith("confirm_delete:"):
        if user.id not in ADMIN_IDS:
            await query.answer("⛔ Yetkiniz yok.", show_alert=True)
            return
        tag = data.split(":", 1)[1]
        deleted = await q.delete_partner(tag)
        msg = f"🗑 <b>#{tag}</b> silindi." if deleted else f"❌ #{tag} bulunamadı."
        await query.edit_message_text(msg, parse_mode=ParseMode.HTML)

    elif data == "cancel":
        await query.edit_message_text("❌ İptal edildi.")


async def handle_new_partner_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Called when user types a partner name after 'save_new_partner' callback."""
    if not ctx.user_data.get("awaiting_partner_name"):
        return  # Not waiting for this

    user = update.effective_user
    tag = update.message.text.strip().lower().lstrip("#").replace(" ", "_")
    pending = _pending_saves.pop(user.id, None)
    ctx.user_data["awaiting_partner_name"] = False

    if not pending or not tag:
        await update.message.reply_html("❌ Bir şeyler ters gitti. Tekrar dene.")
        return

    confirm = await _save_entries(tag, user.id, pending["links"], pending["description"])
    await update.message.reply_html(confirm, disable_web_page_preview=True)
