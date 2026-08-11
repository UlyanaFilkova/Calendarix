"""Handlers for the /start command and the main menu."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

START_TEXT = (
    "👋 Я Calendarix — превращаю посты из Telegram-каналов в твой календарь.\n\n"
    "Пришли мне ссылку на канал:\n"
    "• @username\n"
    "• https://t.me/username"
)


def nav_buttons(back_callback: str) -> list[InlineKeyboardButton]:
    """Build the 'Назад / В главное меню' navigation row."""
    return [
        InlineKeyboardButton("◀️ Назад", callback_data=back_callback),
        InlineKeyboardButton("🏠 В главное меню", callback_data="main_menu"),
    ]


def main_menu() -> InlineKeyboardMarkup:
    """Build the main menu keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("📅 Сегодня", callback_data="today_events"),
            InlineKeyboardButton("📅 Выбрать даты", callback_data="dates_menu"),
        ],
        [
            InlineKeyboardButton("📋 Мои каналы", callback_data="my_sources"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def dates_menu_markup() -> InlineKeyboardMarkup:
    """Build the 'choose dates' keyboard."""
    keyboard = [
        [
             InlineKeyboardButton(
                 "🔍 Сегодня", callback_data="today_events"
             ),
             InlineKeyboardButton(
                 "🔍 Завтра", callback_data="tomorrow_events"
             ),
            ],
        [
            InlineKeyboardButton(
                "📅 На неделю", callback_data="week_events"
            ),
            InlineKeyboardButton(
                "📅 На месяц", callback_data="month_events"
            ),
        ],
        [
            InlineKeyboardButton(
                "🗓 Прошлая неделя", callback_data="prev_week_events"
            ),
            InlineKeyboardButton(
                "🗓 Прошлый месяц", callback_data="prev_month_events"
            ),
        ],
        [
            InlineKeyboardButton(
                "📝 Выбрать дату вручную", callback_data="manual_date"
            )
        ],
        nav_buttons("main_menu"),
    ]
    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command."""
    try:
        await update.message.reply_text(START_TEXT, reply_markup=main_menu())
        print("🚀 /start from", update.effective_user.username)
    except Exception as exc:
        print(f"❌ Error in /start: {exc}")
