"""Event extraction from channel posts via OpenAI GPT."""

import json
from datetime import datetime

from openai import OpenAI

import config

MONTHS = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]
WEEKDAYS = [
    "понедельник", "вторник", "среда", "четверг",
    "пятница", "суббота", "воскресенье",
]

SYSTEM_PROMPT = """Ты — анализатор текста для календаря событий.
Извлеки из сообщения информацию о событии.

Верни ТОЛЬКО JSON, без пояснений:
{
"title": "название события или null",
"date": "YYYY-MM-DD HH:MM или null",
"end_date": "YYYY-MM-DD HH:MM или null",
"location": "место проведения или null",
"description": "краткое описание или null",
"tags": ["массив", "ключевых", "слов"],
"category": "музыка/спорт/образование/другое или null",
"price": "бесплатно/1000₽/от 500₽ или null",
"event_type": "онлайн/офлайн/гибрид",
"image_url": "ссылка на картинку или null",
"external_url": "внешняя ссылка или null"
}

Правила для дат:

Сегодня: {current_date}, день недели: {day_of_week}

"завтра" = текущая дата + 1 день

"послезавтра" = текущая дата + 2 дня

"в пятницу", "в эту субботу" = ближайший день с таким названием

"на следующей неделе" = +7 дней

Если год не указан — использовать 2026

Если время не указано — 00:00

Если в тексте нет информации о событии с датой — верни null для всех полей."""


class EventExtractor:
    """Extracts event data from a message text using GPT."""

    def __init__(self):
        self.client = OpenAI(api_key=config.OPENAI_API_KEY)

    def extract(self, text: str, current_date: datetime) -> dict | None:
        """Send text to GPT and return the extracted event, if any."""
        prompt = SYSTEM_PROMPT.format(
            current_date=f"{current_date.day} "
                         f"{MONTHS[current_date.month - 1]}",
            day_of_week=WEEKDAYS[current_date.weekday()],
        )
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": text},
                ],
            )
            result = json.loads(response.choices[0].message.content)

            if not result.get("date"):
                return None

            result["event_date"] = _parse_datetime(result.pop("date"))
            if not result["event_date"]:
                return None
            if result.get("end_date"):
                result["end_date"] = _parse_datetime(result["end_date"])

            print("✅ Event extracted from text")
            return result
        except json.JSONDecodeError as exc:
            print(f"❌ GPT returned invalid JSON: {exc}")
            return None
        except Exception as exc:
            print(f"❌ GPT request failed: {exc}")
            return None


def _parse_datetime(value: str) -> datetime | None:
    """Parse an ISO datetime string, tolerating missing seconds."""
    value = value.strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None
