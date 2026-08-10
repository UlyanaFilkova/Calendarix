"""Channel URL normalization helpers."""

import re

import config

# Extract username from @username, t.me/username or https://t.me/username
USERNAME_PATTERN = re.compile(
    r"(?:t\.me/|@)([A-Za-z0-9_]{5,})"
)


def normalize_channel_url(url: str) -> str:
    """Normalize a channel reference to @username."""
    url = url.strip()
    match = USERNAME_PATTERN.search(url)
    if match:
        return f"@{match.group(1)}"
    # Unknown format: keep as-is with a leading @
    return url if url.startswith("@") else f"@{url}"
