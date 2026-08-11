"""Bot Service entry point: env loading, DB init, handler registration."""

import os
import random
from datetime import datetime

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

from database import Event, SessionLocal, Source, init_db
from handlers.add_source import add_source
from handlers.calendar import (
    handle_manual_date_input,
    manual_date,
    show_month,
    show_prev_month,
    show_prev_week,
    show_today,
    show_tomorrow,
    show_week,
)
from handlers.sources import (
    cancel_delete,
    confirm_delete_source,
    delete_source,
    rescan_all,
    show_sources,
)
from handlers.start import (
    dates_menu_markup,
    main_menu,
    nav_buttons,
    start,
)
from services.rabbitmq_client import RabbitMQClient

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
RABBITMQ_URL = os.getenv("RABBITMQ_URL")


def handle_parse_result(data: dict) -> None:
    """Save events from a parse result into the database."""
    session = SessionLocal()
    try:
        saved = 0
        updated = 0
        channel_title = data.get("channel_title")
        if channel_title and data.get("source_id"):
            source = (
                session.query(Source)
                .filter(Source.id == data["source_id"])
                .first()
            )
            if source and source.name != channel_title:
                source.name = channel_title
        for event_data in data.get("events", []):
            fields = {
                "title": event_data.get("title") or "Без названия",
                "description": event_data.get("description"),
                "tags": event_data.get("tags"),
                "category": event_data.get("category"),
                "price": event_data.get("price"),
                "image_url": event_data.get("image_url"),
                "event_date": _parse_datetime(event_data.get("event_date")),
                "end_date": _parse_datetime(event_data.get("end_date")),
                "location": event_data.get("location"),
                "url": event_data.get("url"),
                "original_text": event_data.get("original_text") or "",
                "raw_data": event_data.get("raw_data"),
            }
            post_url = event_data.get("post_url")
            existing = None
            if post_url:
                existing = (
                    session.query(Event)
                    .filter(Event.post_url == post_url)
                    .first()
                )
            if existing:
                for key, value in fields.items():
                    setattr(existing, key, value)
                updated += 1
                continue
            session.add(Event(
                source_id=data.get("source_id"),
                user_id=data.get("user_id"),
                post_url=post_url or "",
                **fields,
            ))
            saved += 1
        session.commit()
        print(f"💾 Saved {saved} new, updated {updated} events "
              f"(source {data.get('source_id')})")
    except Exception as exc:
        session.rollback()
        print(f"❌ Failed to save parse result: {exc}")
    finally:
        session.close()


def _parse_datetime(value) -> datetime | None:
    """Convert an ISO string into a datetime, if possible."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


async def handle_text(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Route text messages: manual date input vs. adding a channel."""
    if context.user_data.get("awaiting_date"):
        await handle_manual_date_input(update, context)
    else:
        await add_source(update, context)


async def handle_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Route inline buttons by callback_data."""
    query = update.callback_query
    data = query.data

    if data == "main_menu":
        context.user_data.pop("awaiting_date", None)
        await query.answer()
        await query.message.reply_text(
            "🏠 Главное меню:", reply_markup=main_menu()
        )
    elif data == "dates_menu":
        context.user_data.pop("awaiting_date", None)
        await query.answer()
        await query.message.reply_text(
            "📅 Выбери период:", reply_markup=dates_menu_markup()
        )
    elif data == "today_events":
        await show_today(update, context)
    elif data == "tomorrow_events":
        await show_tomorrow(update, context)
    elif data == "week_events":
        await show_week(update, context)
    elif data == "month_events":
        await show_month(update, context)
    elif data == "prev_week_events":
        await show_prev_week(update, context)
    elif data == "prev_month_events":
        await show_prev_month(update, context)
    elif data == "manual_date":
        await manual_date(update, context)
    elif data == "my_sources":
        await show_sources(update, context)
    elif data == "rescan_all":
        await rescan_all(update, context)
    elif data == "cancel_delete":
        await cancel_delete(update, context)
    elif data.startswith("delete_source_"):
        await delete_source(update, context)
    elif data.startswith("confirm_delete_"):
        await confirm_delete_source(update, context)
    elif data == "how_to_add":
        await query.answer()
        await query.message.reply_text(
            "📖 Как добавить канал:\n\n"
            "Просто пришли мне ссылку на канал в чат:\n"
            "• @username\n"
            "• https://t.me/username\n\n"
            "Я сохраню его в твой список.",
            reply_markup=InlineKeyboardMarkup(
                [nav_buttons("my_sources")]
            ),
        )
    else:
        await query.answer("🤷 Неизвестная кнопка")


RESCAN_MIN_MINUTES = 15
RESCAN_MAX_MINUTES = 40


def periodic_rescan(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Re-scan all active channels and schedule the next scan at random."""
    rabbitmq = context.bot_data.get("rabbitmq")
    if not rabbitmq:
        return
    session = SessionLocal()
    try:
        sources = (
            session.query(Source)
            .filter(Source.is_active == True)
            .all()
        )
        for source in sources:
            rabbitmq.send_parse_request(
                source.id, source.url, source.user_id
            )
        print(f"🔄 Periodic rescan queued for {len(sources)} channels")
    except Exception as exc:
        print(f"❌ Periodic rescan failed: {exc}")
    finally:
        session.close()

    next_in = random.randint(
        RESCAN_MIN_MINUTES, RESCAN_MAX_MINUTES
    ) * 60
    context.job_queue.run_once(
        periodic_rescan, when=next_in, name="periodic_rescan"
    )
    print(f"🕐 Next rescan in {next_in // 60} minutes")


def main() -> None:
    """Initialize and run the bot."""
    rabbitmq = None
    try:
        init_db()

        if not BOT_TOKEN:
            raise ValueError("BOT_TOKEN is not set. Check your .env file.")

        application: Application = (
            ApplicationBuilder().token(BOT_TOKEN).build()
        )

        if RABBITMQ_URL:
            rabbitmq = RabbitMQClient(RABBITMQ_URL)
            rabbitmq.connect()
            rabbitmq.start_consuming(handle_parse_result)
            application.bot_data["rabbitmq"] = rabbitmq

        application.add_handler(CommandHandler("start", start))
        application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)
        )
        application.add_handler(CallbackQueryHandler(handle_callback))

        if rabbitmq:
            first_in = random.randint(
                RESCAN_MIN_MINUTES, RESCAN_MAX_MINUTES
            ) * 60
            application.job_queue.run_once(
                periodic_rescan, when=first_in, name="periodic_rescan"
            )
            print(
                f"🕐 First rescan in {first_in // 60} minutes, "
                f"then every {RESCAN_MIN_MINUTES}-{RESCAN_MAX_MINUTES} "
                "minutes"
            )

        print("🤖 Bot started, waiting for updates...")
        application.run_polling()
    except ValueError as exc:
        print(f"❌ {exc}")
    except Exception as exc:
        print(f"❌ Unexpected error: {exc}")
    finally:
        if rabbitmq:
            rabbitmq.close()


if __name__ == "__main__":
    main()
