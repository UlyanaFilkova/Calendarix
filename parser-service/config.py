"""Parser Service configuration: loads and validates env variables."""

import os

from dotenv import load_dotenv

load_dotenv()

REQUIRED_VARS = {
    "TG_API_ID": "API ID from my.telegram.org",
    "TG_API_HASH": "API hash from my.telegram.org",
    "TG_PHONE": "phone number of the Telegram account",
    "OPENAI_API_KEY": "OpenAI API key",
    "RABBITMQ_URL": "RabbitMQ connection string",
}


def _require_env(name: str, hint: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Missing required env variable {name} ({hint}). "
            f"Check your .env file."
        )
    return value


TG_API_ID = _require_env("TG_API_ID", REQUIRED_VARS["TG_API_ID"])
TG_API_HASH = _require_env("TG_API_HASH", REQUIRED_VARS["TG_API_HASH"])
TG_PHONE = _require_env("TG_PHONE", REQUIRED_VARS["TG_PHONE"])
OPENAI_API_KEY = _require_env(
    "OPENAI_API_KEY", REQUIRED_VARS["OPENAI_API_KEY"]
)
RABBITMQ_URL = _require_env(
    "RABBITMQ_URL", REQUIRED_VARS["RABBITMQ_URL"]
)
