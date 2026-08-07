"""Handler for the user's channel list."""

from telegram import Update
from telegram.ext import ContextTypes

from database import Event, SessionLocal, Source

from handlers.calendar import _answer


async def show_sources(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show the user's channels with event counts."""
    user_id = update.effective_user.id

    session = SessionLocal()
    try:
        sources = (
            session.query(Source)
            .filter(Source.user_id == user_id)
            .all()
        )

        if not sources:
            await _answer(
                update,
                "📋 У тебя пока нет каналов.\n\n"
                "Пришли мне ссылку на канал — например, @username.",
            )
            print(f"📋 Empty channel list (user {user_id})")
            return

        lines = [f"📋 Твои каналы ({len(sources)}):\n"]
        for source in sources:
            event_count = (
                session.query(Event)
                .filter(
                    Event.source_id == source.id,
                    Event.user_id == user_id,
                )
                .count()
            )
            lines.append(
                f"• {source.title}\n"
                f"  {source.url} — {event_count} событий"
            )

        await _answer(update, "\n".join(lines))
        print(f"✅ Shown {len(sources)} channels (user {user_id})")
    except Exception as exc:
        print(f"❌ Failed to list channels: {exc}")
        await _answer(
            update, "⚠️ Не удалось получить список каналов. Попробуй позже."
        )
    finally:
        session.close()
