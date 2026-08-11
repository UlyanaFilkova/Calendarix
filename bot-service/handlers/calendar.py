"""Calendar handlers: today, tomorrow, week, month and manual date views."""

from datetime import datetime, timedelta, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from sqlalchemy.orm import joinedload

from database import Event, SessionLocal
from handlers.start import nav_buttons

WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
MONTHS = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]

EMPTY_TEXT = "📭 Пока событий нет. Добавь каналы — я буду искать даты!"


def format_event(event: Event) -> str:
    """Format a single event as readable text."""
    has_time = event.event_date.hour != 0 or event.event_date.minute != 0
    time_part = (
        f"🕐 {event.event_date.strftime('%H:%M')} — "
        if has_time else ""
    )
    location = f"\n📍 {event.location}" if event.location else ""
    price = f"\n💵 {event.price}" if event.price else ""
    source = event.source.title if event.source else "—"
    return (
        f"{time_part}{event.title}{location}{price}\n"
        f"📎 {source}"
    )


def get_events(user_id: int, start: datetime, end: datetime) -> list[Event]:
    """Return the user's events within the given date range."""
    session = SessionLocal()
    try:
        return (
            session.query(Event)
            .options(joinedload(Event.source))
            .filter(
                Event.user_id == user_id,
                Event.event_date >= start,
                Event.event_date < end,
            )
            .order_by(Event.event_date.asc())
            .all()
        )
    finally:
        session.close()


async def show_today(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show events happening today."""
    start = _today_start()
    await _show_range(
        update, context, start, start + timedelta(days=1),
        f"🔍 События на сегодня ({_format_date(start)}):",
        back="main_menu",
    )


async def show_tomorrow(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show events happening tomorrow."""
    start = _today_start() + timedelta(days=1)
    await _show_range(
        update, context, start, start + timedelta(days=1),
        f"🔍 События на завтра ({_format_date(start)}):",
        back="dates_menu",
    )


async def show_week(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show events for the next 7 days, grouped by day."""
    start = _today_start()
    end = start + timedelta(days=7)
    await _show_range(
        update, context, start, end,
        f"📅 События на неделю "
        f"({_format_date(start)} — {_format_date(end - timedelta(days=1))}):",
        back="dates_menu",
    )


async def show_month(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show events for the next 30 days, grouped by day."""
    start = _today_start()
    end = start + timedelta(days=30)
    await _show_range(
        update, context, start, end,
        f"📅 События на месяц "
        f"({_format_date(start)} — {_format_date(end - timedelta(days=1))}):",
        back="dates_menu",
    )


async def show_prev_week(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show events for the previous 7 days, grouped by day."""
    today_start = _today_start()
    start = today_start - timedelta(days=7)
    await _show_range(
        update, context, start, today_start,
        f"🗓 События за прошлую неделю "
        f"({_format_date(start)} — {_format_date(today_start - timedelta(days=1))}):",
        back="dates_menu",
    )


async def show_prev_month(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show events for the previous 30 days, grouped by day."""
    today_start = _today_start()
    start = today_start - timedelta(days=30)
    await _show_range(
        update, context, start, today_start,
        f"🗓 События за прошлый месяц "
        f"({_format_date(start)} — {_format_date(today_start - timedelta(days=1))}):",
        back="dates_menu",
    )


async def manual_date(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Ask the user to type a date."""
    context.user_data["awaiting_date"] = True
    await _answer(
        update,
        "📝 Напиши дату в формате ДД.ММ.ГГГГ\n"
        "Например: 15.08.2026",
        reply_markup=InlineKeyboardMarkup([nav_buttons("dates_menu")]),
    )


async def handle_manual_date_input(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show events for a date typed by the user."""
    text = update.message.text.strip()
    date = _parse_user_date(text)
    if not date:
        await update.message.reply_text(
            "🤔 Не понял дату. Формат: ДД.ММ.ГГГГ\nНапример: 15.08.2026",
            reply_markup=InlineKeyboardMarkup([nav_buttons("dates_menu")]),
        )
        return
    context.user_data.pop("awaiting_date", None)
    start = datetime(date.year, date.month, date.day)
    await _show_range(
        update, context, start, start + timedelta(days=1),
        f"📅 События на {_format_date(start)}:",
        back="dates_menu",
    )


def _today_start() -> datetime:
    """Start of today in the bot's timezone."""
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _parse_user_date(text: str) -> datetime | None:
    """Parse a manually entered date (ДД.ММ.ГГГГ / ДД.ММ.ГГ / ДД.ММ)."""
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%d.%m"):
        try:
            date = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if fmt == "%d.%m":
            date = date.replace(year=datetime.now().year)
        return date
    return None


async def _show_range(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    start: datetime,
    end: datetime,
    header: str,
    back: str,
) -> None:
    """Render events in a date range as a new message with nav buttons."""
    user_id = update.effective_user.id
    events = get_events(user_id, start, end)
    reply_markup = InlineKeyboardMarkup([nav_buttons(back)])

    if not events:
        await _answer(update, EMPTY_TEXT, reply_markup)
        print(f"📭 No events in range (user {user_id})")
        return

    now = datetime.now(timezone.utc)
    lines = [header, ""]
    current_day = None
    for event in events:
        day = event.event_date.date()
        if day != current_day:
            current_day = day
            lines.append(f"—— {_format_day(day, now)} ——")
        lines.append(format_event(event))

    await _answer(update, "\n".join(lines), reply_markup)
    print(f"✅ Shown {len(events)} events (user {user_id})")


def _format_date(date: datetime) -> str:
    """Format a date, e.g. "7 августа"."""
    return f"{date.day} {MONTHS[date.month - 1]}"


def _format_day(day, now: datetime) -> str:
    """Format a weekday label, e.g. "Пн, 7 августа (сегодня)"."""
    weekday = WEEKDAYS[day.weekday()]
    label = f"{weekday}, {_format_date(day)}"
    if day == now.date():
        label += " (сегодня)"
    elif day == now.date() + timedelta(days=1):
        label += " (завтра)"
    return label


async def _answer(
    update: Update, text: str, reply_markup=None
) -> None:
    """Send a NEW message, either to a callback query or a plain message."""
    if update.callback_query:
        await update.callback_query.answer()
        await update.effective_message.reply_text(
            text, reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)
