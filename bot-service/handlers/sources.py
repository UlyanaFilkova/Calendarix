"""Handler for the user's channel list."""

import html

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from database import Event, SessionLocal, Source

from handlers.calendar import _answer
from handlers.start import nav_buttons


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
        ],
        nav_buttons("my_sources"),
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
            label = html.escape(source.title)
            if source.name and source.name != source.title:
                label = (
                    f"{html.escape(source.name)} "
                    f"({html.escape(source.title)})"
                )
            lines.append(
                f"• {label} — {event_count} событий"
            )
            keyboard.append(
                [
                    InlineKeyboardButton(
                        f"🗑 {source.title}",
                        callback_data=f"delete_source_{source.id}",
                    )
                ]
            )

        keyboard.append(
            [
                InlineKeyboardButton(
                    "🔄 Обновить все каналы", callback_data="rescan_all"
                )
            ]
        )
        keyboard.append(
            [
                InlineKeyboardButton(
                    "➕ Добавить канал", callback_data="how_to_add"
                )
            ]
        )
        keyboard.append(nav_buttons("main_menu"))

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


async def rescan_all(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Send refresh requests for all of the user's channels."""
    user_id = update.effective_user.id
    nav = InlineKeyboardMarkup([nav_buttons("my_sources")])

    rabbitmq = context.bot_data.get("rabbitmq")
    if not rabbitmq:
        await _answer(
            update,
            "⚠️ Сервис сканирования сейчас недоступен. Попробуй позже.",
            nav,
        )
        return

    session = SessionLocal()
    try:
        sources = (
            session.query(Source)
            .filter(Source.user_id == user_id)
            .all()
        )
        sent = 0
        for source in sources:
            if rabbitmq.send_parse_request(source.id, source.url, user_id):
                sent += 1
        await _answer(
            update,
            f"🔄 Отправил запросы на обновление {sent} из {len(sources)} "
            "каналов. События обновятся через несколько минут.",
            nav,
        )
        print(f"🔄 Manual refresh queued for {sent}/{len(sources)} "
              f"channels (user {user_id})")
    except Exception as exc:
        print(f"❌ Failed to refresh channels: {exc}")
        await _answer(
            update,
            "⚠️ Не удалось запустить обновление. Попробуй позже.",
            nav,
        )
    finally:
        session.close()


async def delete_source(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Ask for confirmation before removing a channel."""
    source_id = int(update.callback_query.data.split("_")[-1])
    user_id = update.effective_user.id
    nav = InlineKeyboardMarkup([nav_buttons("my_sources")])

    session = SessionLocal()
    try:
        source = (
            session.query(Source)
            .filter(Source.id == source_id, Source.user_id == user_id)
            .first()
        )
        if not source:
            await _answer(
                update, "⚠️ Канал не найден. Возможно, он уже удалён.", nav
            )
            return

        await _answer(
            update,
            f"Точно удалить канал {html.escape(source.title)}?\n"
            "Все его события тоже будут удалены.",
            reply_markup=_delete_confirm_markup(source.id),
        )
        print(f"🗑 Asked to confirm deletion of {source.title} "
              f"(user {user_id})")
    except Exception as exc:
        print(f"❌ Failed to open delete confirmation: {exc}")
        await _answer(
            update,
            "⚠️ Не удалось открыть подтверждение. Попробуй позже.",
            nav,
        )
    finally:
        session.close()


async def confirm_delete_source(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Remove a channel and its events."""
    source_id = int(update.callback_query.data.split("_")[-1])
    user_id = update.effective_user.id
    nav = InlineKeyboardMarkup([nav_buttons("my_sources")])

    session = SessionLocal()
    try:
        source = (
            session.query(Source)
            .filter(Source.id == source_id, Source.user_id == user_id)
            .first()
        )
        if not source:
            await _answer(
                update, "⚠️ Канал не найден. Возможно, он уже удалён.", nav
            )
            return

        deleted_events = (
            session.query(Event)
            .filter(Event.source_id == source.id)
            .delete(synchronize_session=False)
        )
        session.delete(source)
        session.commit()

        await _answer(
            update,
            f"🗑 Канал {html.escape(source.title)} удалён вместе с "
            f"{deleted_events} событиями.",
            nav,
        )
        print(f"🗑 Deleted {source.title} and {deleted_events} events "
              f"(user {user_id})")
    except Exception as exc:
        session.rollback()
        print(f"❌ Failed to delete channel: {exc}")
        await _answer(
            update,
            "⚠️ Не удалось удалить канал. Попробуй позже.",
            nav,
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



