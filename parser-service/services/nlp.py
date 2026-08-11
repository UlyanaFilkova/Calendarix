"""Event extraction from channel posts via a Groq LLM."""

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
# Belarusian (belaruskaia mova) month and weekday names, so the LLM
# can resolve dates like "05.09 (субота)" or "12 сакавіка".
BELARUSIAN_MONTHS = [
    "студзень", "люты", "сакавік", "красавік", "май", "чэрвень",
    "ліпень", "жнівень", "верасень", "кастрычнік", "лістапад", "снежань",
]
BELARUSIAN_WEEKDAYS = [
    "панядзелак", "аўторак", "серада", "чацвер",
    "пятніца", "субота", "нядзеля",
]

SYSTEM_PROMPT = """Ты — анализатор текста для календаря событий.
Извлеки из сообщения информацию о событии.

Сообщение может быть написано на русском ИЛИ белорусском языке.
Обрабатывай оба языка одинаково. Название события можно оставлять
на языке оригинала.

Верни ТОЛЬКО валидный JSON объект, без пояснений:
{
"title": "название события или null",
"date": "YYYY-MM-DD HH:MM или null",
"end_date": "YYYY-MM-DD HH:MM или null",
"location": "место проведения: конкретный адрес, заведение или точка сбора/отправления, если она указана; иначе город или район. null, если неизвестно",
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

"в пятницу", "в эту субботу", "у суботу" = ближайший день с таким названием

"на следующей неделе" = +7 дней

Дни недели распознавай и по-белорусски: панядзелак, аўторак, серада,
чацвер, пятніца, субота, нядзеля.

Дата может быть записана как "05.09" (день.месяц), "05.09.2026",
"5 сентября", "12 сакавіка", "05.09 (субота)" — в любом случае
верни дату в формате "YYYY-MM-DD HH:MM".

Месяцы распознавай по-русски и по-белорусски (студзень, люты, сакавік,
красавік, май, чэрвень, ліпень, жнівень, верасень, кастрычнік, лістапад,
снежань).

Если год не указан — использовать {current_year}

Если время не указано — 00:00

Если в тексте нет информации о событии с датой — верни null для всех полей.

НЕ считай событием сообщения, которые просто делятся готовым материалом:
запись выступления, ссылка на видео/YouTube/VK, подкаст, статья, трансляция
уже прошедшего события. Если пост — это анонс или ссылка без даты и места
проведения реального мероприятия — верни null для всех полей.

Если в тексте есть дата события — title ОБЯЗАТЕЛЬНО должен быть заполнен:
это краткое название события (праздник, концерт, лекция, мероприятие).
Пример: "Сегодня совершается память пророка Илии" → "Память пророка Илии"."""


class LLMError(Exception):
    """Raised when the LLM request itself fails (quota, network, ...)."""


class EventExtractor:
    """Extracts event data from a message text using a Groq LLM."""

    def __init__(self):
        self.client = OpenAI(
            api_key=config.LLM_API_KEY,
            base_url=config.LLM_BASE_URL,
        )

    def extract(self, text: str, current_date: datetime) -> dict | None:
        """Send text to the LLM and return the extracted event, if any.

        Returns None when the message legitimately has no event.
        Raises LLMError when the LLM request itself fails.
        """
        prompt = (
            SYSTEM_PROMPT
            .replace(
                "{current_date}",
                f"{current_date.day} {MONTHS[current_date.month - 1]}",
            )
            .replace("{day_of_week}", WEEKDAYS[current_date.weekday()])
            .replace("{current_year}", str(current_date.year))
        )
        for attempt in range(2):
            try:
                response = self.client.chat.completions.create(
                    model=config.LLM_MODEL,
                    temperature=0,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": text},
                    ],
                )
                result = json.loads(_clean_json(response.choices[0].message.content))

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
                print(f"❌ LLM returned invalid JSON: {exc}")
                continue
            except Exception as exc:
                print(f"❌ LLM request failed: {exc}")
                raise LLMError(str(exc)) from exc
        raise LLMError("LLM returned invalid JSON twice")


def _clean_json(content: str) -> str:
    """Strip markdown fences and surrounding noise from an LLM reply."""
    content = content.strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.lower().startswith("json"):
            content = content[4:]
    return content.strip()


def _parse_datetime(value: str) -> datetime | None:
    """Parse an ISO datetime string, tolerating missing seconds.

    Also accepts common "DD.MM" / "DD.MM.YYYY" styles as a fallback.
    """
    value = value.strip()
    for fmt in (
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d.%m.%Y %H:%M",
        "%d.%m.%Y",
    ):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None
