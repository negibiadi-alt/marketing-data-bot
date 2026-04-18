from __future__ import annotations
import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import PHOTOS_DIR, ADMIN_IDS
from database import queries as q
from utils.parser import extract_hashtags

logger = logging.getLogger(__name__)

# user_id -> file_id (waiting for partner assignment)
_pending_photos: dict[int, str] = {}


async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await q.ensure_user(user.id, user.username)

    photo = update.message.photo[-1]  # Largest size
    file_id = photo.file_id
    caption = update.message.caption or ""
    tags = extract_hashtags(caption)

    if tags:
        # Save directly under first tag
        tag = tags[0]
        partner_id = await q.get_or_create_partner(tag, user.id)
        file_path = await _download_photo(ctx, file_id, tag)
        await q.add_entry(
            partner_id=partner_id,
            user_id=user.id,
            entry_type="photo",
            description=caption or None,
            file_path=file_path,
            file_id=file_id,
        )
        await update.message.reply_html(
            f"📸 Fotoğraf <b>#{tag}</b> altına kaydedildi."
        )
    else:
        # Ask which partner
        _pending_photos[user.id] = file_id
        partners = await q.get_all_partners()
        if not partners:
            await update.message.reply_html(
                "📸 Fotoğraf alındı ama henüz partner yok.\n"
                "Önce bir partner ekleyin: <code>/add #partner</code>"
            )
            return

        keyboard = []
        for p in partners[:10]:  # Max 10 buttons
            keyboard.append([
                InlineKeyboardButton(
                    f"#{p['tag']}", callback_data=f"assign_photo:{p['tag']}"
                )
            ])
        keyboard.append([InlineKeyboardButton("❌ İptal", callback_data="cancel_photo")])

        await update.message.reply_html(
            "📸 Bu fotoğraf hangi partner için?",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )


async def handle_photo_assign(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    data = query.data or ""

    if data == "cancel_photo":
        _pending_photos.pop(user.id, None)
        await query.edit_message_text("❌ Fotoğraf kaydı iptal edildi.")
        return

    if data.startswith("assign_photo:"):
        tag = data.split(":", 1)[1]
        file_id = _pending_photos.pop(user.id, None)
        if not file_id:
            await query.edit_message_text("❌ Bekleyen fotoğraf bulunamadı.")
            return

        partner_id = await q.get_or_create_partner(tag, user.id)
        file_path = await _download_photo(ctx, file_id, tag)
        await q.add_entry(
            partner_id=partner_id,
            user_id=user.id,
            entry_type="photo",
            file_path=file_path,
            file_id=file_id,
        )
        await query.edit_message_text(f"📸 Fotoğraf #{tag} altına kaydedildi.")


async def _download_photo(ctx: ContextTypes.DEFAULT_TYPE, file_id: str, tag: str) -> str:
    """Download photo from Telegram and save to disk. Returns file path."""
    try:
        tag_dir = os.path.join(PHOTOS_DIR, tag)
        os.makedirs(tag_dir, exist_ok=True)
        file = await ctx.bot.get_file(file_id)
        file_path = os.path.join(tag_dir, f"{file_id}.jpg")
        await file.download_to_drive(file_path)
        return file_path
    except Exception as e:
        logger.warning("Could not download photo %s: %s", file_id, e)
        return ""
