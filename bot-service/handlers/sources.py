"""Handler for the user's channel list."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from database import Event, SessionLocal, Source

from handlers.calendar import _answer


def _delete_confirm_markup(source_id: int) -> InlineKeyboardMarkup:
    """Build a confirmation keyboard for deleting a channel."""
    keyboard = [
        [
            InlineKeyboardButton(
                "✅ Да, удалить",
                callback_data=f"confirm_delete_{source_id}",
            ),
            InlineKeyboardButton(
                "❌ Отмена",
                callback_data="cancel_delete",
            ),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


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
        keyboard = []
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
            keyboard.append(
                [
                    InlineKeyboardButton(
                        f"🗑 {source.title}",
                        callback_data=f"delete_source_{source.id}",
                    )
                ]
            )

        await _answer(
            update,
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        print(f"✅ Shown {len(sources)} channels (user {user_id})")
    except Exception as exc:
        print(f"❌ Failed to list channels: {exc}")
        await _answer(
            update, "⚠️ Не удалось получить список каналов. Попробуй позже."
        )
    finally:
        session.close()


async def delete_source(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Ask for confirmation before removing a channel."""
    query = update.callback_query
    await query.answer()

    source_id = int(query.data.split("_")[-1])
    user_id = update.effective_user.id

    session = SessionLocal()
    try:
        source = (
            session.query(Source)
            .filter(Source.id == source_id, Source.user_id == user_id)
            .first()
        )
        if not source:
            await query.edit_message_text(
                "⚠️ Канал не найден. Возможно, он уже удалён."
            )
            return

        await query.edit_message_text(
            f"Точно удалить канал {source.title}?\n"
            "Все его события тоже будут удалены.",
            reply_markup=_delete_confirm_markup(source.id),
        )
        print(f"🗑 Asked to confirm deletion of {source.title} "
              f"(user {user_id})")
    except Exception as exc:
        print(f"❌ Failed to open delete confirmation: {exc}")
        await query.edit_message_text(
            "⚠️ Не удалось открыть подтверждение. Попробуй позже."
        )
    finally:
        session.close()


async def confirm_delete_source(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Remove a channel and its events."""
    query = update.callback_query
    await query.answer()

    source_id = int(query.data.split("_")[-1])
    user_id = update.effective_user.id

    session = SessionLocal()
    try:
        source = (
            session.query(Source)
            .filter(Source.id == source_id, Source.user_id == user_id)
            .first()
        )
        if not source:
            await query.edit_message_text(
                "⚠️ Канал не найден. Возможно, он уже удалён."
            )
            return

        deleted_events = (
            session.query(Event)
            .filter(Event.source_id == source.id)
            .delete(synchronize_session=False)
        )
        session.delete(source)
        session.commit()

        await query.edit_message_text(
            f"🗑 Канал {source.title} удалён вместе с "
            f"{deleted_events} событиями."
        )
        print(f"🗑 Deleted {source.title} and {deleted_events} events "
              f"(user {user_id})")
    except Exception as exc:
        session.rollback()
        print(f"❌ Failed to delete channel: {exc}")
        await query.edit_message_text(
            "⚠️ Не удалось удалить канал. Попробуй позже."
        )
    finally:
        session.close()


async def cancel_delete(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Cancel a channel deletion and go back to the source list."""
    query = update.callback_query
    await query.answer()
    await show_sources(update, context)


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
