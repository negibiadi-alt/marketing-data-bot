from __future__ import annotations
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from database import queries as q
from utils.parser import is_only_hashtag, is_only_url
from utils.formatter import format_partner_list, relative_time
from ai.claude import ai

logger = logging.getLogger(__name__)


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


async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    text = update.message.text or ""
    await q.ensure_user(user.id, user.username)

    from config import ADMIN_IDS

    # 1. Only a hashtag → partner query
    tag = is_only_hashtag(text)
    if tag:
        partner, entries = await q.get_partner_entries(tag)
        if not partner:
            await update.message.reply_html(
                f"❓ <b>#{tag}</b> partneri bulunamadı.\n"
                f"Eklemek için: <code>/add #{tag} https://link açıklama</code>"
            )
            return
        msg = format_partner_list(partner, entries)
        keyboard = _partner_keyboard(partner["id"], tag, user.id in ADMIN_IDS)
        await update.message.reply_html(msg, reply_markup=keyboard, disable_web_page_preview=True)
        return

    # 2. Only a URL → link lookup
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
                f"Eklemek için: <code>/add #partner {url}</code>"
            )
        return

    # 3. Natural language → Claude AI
    await update.message.chat.send_action("typing")
    reply = await ai.chat(user.id, user.username, text)
    await update.message.reply_html(reply)


async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    user = update.effective_user
    from config import ADMIN_IDS

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
        await query.message.reply_html(
            "\n".join(lines), disable_web_page_preview=True
        )

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
        if deleted:
            await query.edit_message_text(f"🗑 <b>#{tag}</b> ve tüm verileri silindi.", parse_mode=ParseMode.HTML)
        else:
            await query.edit_message_text(f"❌ #{tag} bulunamadı.")

    elif data == "cancel":
        await query.edit_message_text("❌ İptal edildi.")
