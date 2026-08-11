"""Parser Service configuration: loads and validates env variables."""

import os

from dotenv import load_dotenv

load_dotenv()

REQUIRED_VARS = {
    "LLM_API_KEY": "API key from console.groq.com",
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


LLM_API_KEY = _require_env("LLM_API_KEY", REQUIRED_VARS["LLM_API_KEY"])
RABBITMQ_URL = _require_env(
    "RABBITMQ_URL", REQUIRED_VARS["RABBITMQ_URL"]
)

LLM_BASE_URL = os.getenv(
    "LLM_BASE_URL",
    "https://api.cloudflare.com/client/v4/accounts/<account_id>/ai/v1/",
)
LLM_MODEL = os.getenv(
    "LLM_MODEL", "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
)
