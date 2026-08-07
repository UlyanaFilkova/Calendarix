"""Bot Service entry point: env loading, DB init, handler registration."""

import os

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from database import init_db
from handlers.add_source import add_source
from handlers.calendar import show_today, show_week
from handlers.sources import show_sources
from handlers.start import start, main_menu

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")


async def handle_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Route inline buttons by callback_data."""
    query = update.callback_query
    data = query.data

    if data == "today_events":
        await show_today(update, context)
    elif data == "week_events":
        await show_week(update, context)
    elif data == "my_sources":
        await show_sources(update, context)
    elif data == "how_to_add":
        await query.answer()
        await query.edit_message_text(
            "📖 Как добавить канал:\n\n"
            "Просто пришли мне ссылку на канал в чат:\n"
            "• @username\n"
            "• https://t.me/username\n\n"
            "Я сохраню его в твой список.",
            reply_markup=main_menu(),
        )
    else:
        await query.answer("🤷 Неизвестная кнопка")


def main() -> None:
    """Initialize and run the bot."""
    try:
        init_db()

        if not BOT_TOKEN:
            raise ValueError("BOT_TOKEN is not set. Check your .env file.")

        application: Application = (
            ApplicationBuilder().token(BOT_TOKEN).build()
        )

        application.add_handler(CommandHandler("start", start))
        application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, add_source)
        )
        application.add_handler(CallbackQueryHandler(handle_callback))

        print("🤖 Bot started, waiting for updates...")
        application.run_polling()
    except ValueError as exc:
        print(f"❌ {exc}")
    except Exception as exc:
        print(f"❌ Unexpected error: {exc}")


if __name__ == "__main__":
    main()
