"""Telegram channel scanning via Telethon."""

import asyncio
from datetime import datetime

from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.types import Message

import config
from services.nlp import EventExtractor
from utils.url_parser import normalize_channel_url

MIN_TEXT_LENGTH = 30
MAX_ORIGINAL_TEXT = 500


class TelegramReader:
    """Reads recent posts from a channel and extracts events."""

    def __init__(self):
        self.client = TelegramClient(
            "parser_session", config.TG_API_ID, config.TG_API_HASH
        )
        self.extractor = EventExtractor()

    async def connect(self) -> None:
        """Start the Telegram client and authorize."""
        try:
            await self.client.start(phone=config.TG_PHONE)
            print("✅ Telegram client ready")
        except Exception as exc:
            print(f"❌ Telegram authorization failed: {exc}")
            raise

    async def scan_channel(
        self, url: str, limit: int = 10
    ) -> tuple[list[dict], int]:
        """Scan recent posts and return extracted events."""
        channel = normalize_channel_url(url)
        username = channel.lstrip("@")
        events: list[dict] = []

        try:
            messages = await self.client.get_messages(username, limit=limit)
            print(f"📥 Received {len(messages)} messages from {channel}")
        except FloodWaitError as exc:
            print(f"⏳ Flood wait {exc.seconds}s, sleeping...")
            await asyncio.sleep(exc.seconds)
            return events, 0
        except Exception as exc:
            print(f"❌ Cannot read channel {channel}: {exc}")
            return events, 0

        for message in messages:
            if not isinstance(message, Message):
                continue
            text = (message.text or "").strip()
            if not text or len(text) < MIN_TEXT_LENGTH:
                continue

            event = self.extractor.extract(text, datetime.now())
            if not event:
                continue

            event["original_text"] = text[:MAX_ORIGINAL_TEXT]
            event["post_url"] = f"https://t.me/{username}/{message.id}"
            events.append(event)

        print(f"✅ Found {len(events)} events in {channel}")
        return events, len(messages)
