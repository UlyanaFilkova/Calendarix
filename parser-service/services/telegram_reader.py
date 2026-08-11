"""Channel post scanning via the public t.me/s web preview."""

import re
from datetime import datetime
from html import unescape

import requests

from services.nlp import EventExtractor
from utils.url_parser import normalize_channel_url

MIN_TEXT_LENGTH = 30
MAX_ORIGINAL_TEXT = 500

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

TME_S_URL = "https://t.me/s/{username}"

# Start of each message block in the t.me/s HTML
MESSAGE_START_RE = re.compile(
    r'<div class="tgme_widget_message\b[^>]*data-post="([^"]+)"'
)
TEXT_DIV_RE = re.compile(
    r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
    re.S,
)
TIME_RE = re.compile(r'<time datetime="([^"]+)"')
CHANNEL_TITLE_RE = re.compile(
    r'class="tgme_channel_info_header_title"[^>]*>(.*?)</div>',
    re.S,
)


def _clean_html(raw: str) -> str:
    """Convert message HTML into plain text."""
    raw = re.sub(r"<br\s*/?>", "\n", raw)
    raw = re.sub(r"</(div|p)>", "\n", raw)
    raw = re.sub(r"<[^>]+>", "", raw)
    return unescape(raw).strip()


class TelegramReader:
    """Reads recent posts of a public channel via t.me/s preview."""

    def __init__(self):
        self.extractor = EventExtractor()
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def _fetch_page(self, username: str) -> str | None:
        resp = self.session.get(
            TME_S_URL.format(username=username), timeout=30
        )
        if resp.status_code != 200:
            print(
                f"⚠️ Channel @{username}: not found "
                f"(HTTP {resp.status_code})"
            )
            return None
        return resp.text

    @staticmethod
    def _parse_messages(html: str, username: str) -> list[dict]:
        messages = []
        matches = list(MESSAGE_START_RE.finditer(html))
        for idx, match in enumerate(matches):
            post_key = match.group(1)  # e.g. "durov/519"
            end = (
                matches[idx + 1].start()
                if idx + 1 < len(matches)
                else len(html)
            )
            block = html[match.start():end]

            text_match = TEXT_DIV_RE.search(block)
            if not text_match:
                continue
            text = _clean_html(text_match.group(1))
            if not text:
                continue

            time_match = TIME_RE.search(block)
            messages.append(
                {
                    "text": text,
                    "url": f"https://t.me/{post_key}",
                    "date": time_match.group(1) if time_match else None,
                }
            )
        return messages

    @staticmethod
    def _parse_post_date(raw: str | None) -> datetime | None:
        """Parse the post publication datetime from t.me/s markup."""
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return None

    def scan_channel(
        self, url: str, limit: int = 10
    ) -> tuple[list[dict], int]:
        """Scan recent posts and return extracted events."""
        channel = normalize_channel_url(url)
        username = channel.lstrip("@")

        html = self._fetch_page(username)
        if html is None:
            return [], 0, None

        channel_title = self._extract_channel_title(html)
        print(f"📥 Received posts from {channel} ({channel_title!r})")

        messages = self._parse_messages(html, username)
        print(f"📥 Received {len(messages)} messages from {channel}")
        if not messages:
            print(f"⚠️ No posts found in {channel} (private or empty)")
            return [], 0, channel_title

        events: list[dict] = []
        for message in messages[:limit]:
            text = message["text"]
            if len(text) < MIN_TEXT_LENGTH:
                continue

            event = self.extractor.extract(
                text,
                self._parse_post_date(message["date"]) or datetime.now(),
            )
            if not event:
                continue

            event["original_text"] = text[:MAX_ORIGINAL_TEXT]
            event["post_url"] = message["url"]
            events.append(event)

        print(f"✅ Found {len(events)} events in {channel}")
        return events, len(messages), channel_title

    @staticmethod
    def _extract_channel_title(html: str) -> str | None:
        """Extract the channel display name from the t.me/s page."""
        match = CHANNEL_TITLE_RE.search(html)
        if not match:
            return None
        title = _clean_html(match.group(1))
        return title or None
