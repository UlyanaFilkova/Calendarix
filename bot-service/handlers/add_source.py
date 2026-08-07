"""Handler for text messages: adding a channel source."""

import re

from telegram import Update
from telegram.ext import ContextTypes

from database import SessionLocal, Source

# Matches https://t.me/username or @username
CHANNEL_PATTERN = re.compile(
    r"(?:t\.me/([A-Za-z0-9_]{5,})|@([A-Za-z0-9_]{5,}))"
)


def extract_username(text: str) -> str | None:
    """Extract and normalize a username from text as @username."""
    match = CHANNEL_PATTERN.search(text)
    if not match:
        return None
    username = match.group(1) or match.group(2)
    return f"@{username}"


async def add_source(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle a text message containing a channel link."""
    text = (update.message.text or "").strip()

    username = extract_username(text)
    if not username:
        await update.message.reply_text(
            "🤔 Не похоже на ссылку на канал.\n\n"
            "Пришли мне ссылку в формате:\n"
            "• @username\n"
            "• https://t.me/username"
        )
        return

    user_id = update.effective_user.id

    session = SessionLocal()
    try:
        existing = (
            session.query(Source)
            .filter(
                Source.user_id == user_id,
                Source.url == f"https://t.me/{username[1:]}",
            )
            .first()
        )
        if existing:
            await update.message.reply_text(
                f"ℹ️ {username} уже в твоём списке."
            )
            print(f"✅ Channel {username} already in list (user {user_id})")
            return

        source = Source(
            user_id=user_id,
            url=f"https://t.me/{username[1:]}",
            title=username,
            type="telegram",
            is_active=True,
        )
        session.add(source)
        session.commit()

        await update.message.reply_text(
            f"✅ Канал {username} добавлен. "
            "Как только я научусь парсить, сразу найду там события."
        )
        print(f"✅ Added channel {username} (user {user_id})")
    except Exception as exc:
        session.rollback()
        print(f"❌ Failed to add channel: {exc}")
        await update.message.reply_text(
            "⚠️ Не удалось сохранить канал. Попробуй ещё раз позже."
        )
    finally:
        session.close()
