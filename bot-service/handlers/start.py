"""Handlers for the /start command and the main menu."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

START_TEXT = (
    "👋 Я Calendarix — превращаю посты из Telegram-каналов в твой календарь.\n\n"
    "Пришли мне ссылку на канал:\n"
    "• @username\n"
    "• https://t.me/username"
)


def main_menu() -> InlineKeyboardMarkup:
    """Build the main menu keyboard."""
    keyboard = [
        [
            InlineKeyboardButton(
                "➕ Добавить канал", callback_data="how_to_add"
            )
        ],
        [
            InlineKeyboardButton(
                "📅 На неделю", callback_data="week_events"
            ),
            InlineKeyboardButton(
                "🔍 Сегодня", callback_data="today_events"
            ),
        ],
        [
            InlineKeyboardButton(
                "📋 Мои каналы", callback_data="my_sources"
            )
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command."""
    try:
        await update.message.reply_text(START_TEXT, reply_markup=main_menu())
        print("🚀 /start from", update.effective_user.username)
    except Exception as exc:
        print(f"❌ Error in /start: {exc}")
