import asyncio
import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from config import TELEGRAM_TOKEN
from database.db import init_db, close_db
from handlers.commands import (
    cmd_start, cmd_help, cmd_add, cmd_note,
    cmd_partners, cmd_stats, cmd_recent, cmd_search,
    cmd_delete, cmd_export,
)
from handlers.messages import handle_text, handle_callback
from handlers.media import handle_photo, handle_photo_assign

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def post_init(application: Application) -> None:
    await init_db()
    logger.info("Bot started successfully.")


async def post_shutdown(application: Application) -> None:
    await close_db()
    logger.info("Bot shut down.")


def main() -> None:
    app = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("add", cmd_add))
    app.add_handler(CommandHandler("note", cmd_note))
    app.add_handler(CommandHandler("partners", cmd_partners))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("recent", cmd_recent))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CommandHandler("delete", cmd_delete))
    app.add_handler(CommandHandler("export", cmd_export))

    # Photo handler
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    # Callback query handlers (order matters)
    app.add_handler(CallbackQueryHandler(handle_photo_assign, pattern=r"^(assign_photo:|cancel_photo)"))
    app.add_handler(CallbackQueryHandler(handle_callback))

    # Text message handler (catch-all, must be last)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Starting polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
