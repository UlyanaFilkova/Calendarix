"""Calendar handlers: today and next-week events."""

from datetime import datetime, timedelta, timezone

from telegram import Update
from telegram.ext import ContextTypes

from sqlalchemy.orm import joinedload

from database import Event, SessionLocal

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
    user_id = update.effective_user.id

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_start = today_start + timedelta(days=1)

    events = get_events(user_id, today_start, tomorrow_start)

    if not events:
        await _answer(update, EMPTY_TEXT)
        print(f"📭 No events today (user {user_id})")
        return

    lines = [f"🔍 События на сегодня ({_format_date(today_start)}):\n"]
    lines.extend(format_event(ev) for ev in events)
    await _answer(update, "\n".join(lines))
    print(f"✅ Shown {len(events)} today events (user {user_id})")


async def show_week(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show events for the next 7 days, grouped by day."""
    user_id = update.effective_user.id

    now = datetime.now(timezone.utc)
    week_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_end = week_start + timedelta(days=7)

    events = get_events(user_id, week_start, week_end)

    if not events:
        await _answer(update, EMPTY_TEXT)
        print(f"📭 No events this week (user {user_id})")
        return

    lines = [f"📅 События на неделю ({_format_date(week_start)} — "
             f"{_format_date(week_end - timedelta(days=1))}):\n"]
    current_day = None
    for event in events:
        day = event.event_date.date()
        if day != current_day:
            current_day = day
            day_label = _format_day(day, now)
            lines.append(f"\n—— {day_label} ——")
        lines.append(format_event(event))

    await _answer(update, "\n".join(lines))
    print(f"✅ Shown {len(events)} week events (user {user_id})")


async def show_prev_week(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show events for the previous 7 days, grouped by day."""
    user_id = update.effective_user.id

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    prev_start = today_start - timedelta(days=7)

    events = get_events(user_id, prev_start, today_start)

    if not events:
        await _answer(update, EMPTY_TEXT)
        print(f"📭 No events last week (user {user_id})")
        return

    lines = [f"🗓 События за прошлую неделю ({_format_date(prev_start)} — "
             f"{_format_date(today_start - timedelta(days=1))}):\n"]
    current_day = None
    for event in events:
        day = event.event_date.date()
        if day != current_day:
            current_day = day
            day_label = _format_day(day, now)
            lines.append(f"\n—— {day_label} ——")
        lines.append(format_event(event))

    await _answer(update, "\n".join(lines))
    print(f"✅ Shown {len(events)} last-week events (user {user_id})")


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
    """Reply either to a callback query or a plain message."""
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text, reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)
