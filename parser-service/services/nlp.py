"""Event extraction from channel posts via a DSPy program."""

import os
from datetime import datetime
from typing import Literal, Optional

import dspy

import config

MONTHS = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]
WEEKDAYS = [
    "понедельник", "вторник", "среда", "четверг",
    "пятница", "суббота", "воскресенье",
]

COMPILED_PROGRAM_PATH = os.getenv(
    "COMPILED_PROGRAM_PATH",
    "/app/data/compiled_program.json",
)

Category = Literal["музыка", "спорт", "образование", "другое"]
EventType = Literal["онлайн", "офлайн", "гибрид"]


class EventSignature(dspy.Signature):
    """Ты — анализатор текста для календаря событий.

    Извлеки из сообщения информацию о событии. Сообщение может быть
    написано на русском ИЛИ белорусском языке. Обрабатывай оба языка
    одинаково. Название события можно оставлять на языке оригинала.

    Правила для дат:

    "завтра" = текущая дата + 1 день, "послезавтра" = текущая дата + 2 дня.
    "в пятницу", "в эту субботу", "у суботу" = ближайший день с таким
    названием. "на следующей неделе" = +7 дней.

    Дни недели распознавай и по-белорусски: панядзелак, аўторак, серада,
    чацвер, пятніца, субота, нядзеля. Месяцы распознавай по-русски и
    по-белорусски (студзень, люты, сакавік, красавік, май, чэрвень, ліпень,
    жнівень, верасень, кастрычнік, лістапад, снежань).

    Дата может быть записана как "05.09" (день.месяц), "05.09.2026",
    "5 сентября", "12 сакавіка", "05.09 (субота)" — в любом случае верни
    дату в формате "YYYY-MM-DD HH:MM". Если год не указан — использовать
    current_year. Если время не указано — 00:00.

    Если в тексте нет информации о событии с датой — верни null для всех
    полей.

    НЕ считай событием сообщения, которые просто делятся готовым материалом:
    запись выступления, ссылка на видео/YouTube/VK, подкаст, статья,
    трансляция уже прошедшего события. Если пост — это анонс или ссылка
    без даты и места проведения реального мероприятия — верни null для
    всех полей.

    Если в тексте есть дата события — title ОБЯЗАТЕЛЬНО должен быть
    заполнен: это краткое название события (праздник, концерт, лекция,
    мероприятие).
    """

    text: str = dspy.InputField(
        desc="Текст поста из Telegram-канала (русский или белорусский)"
    )
    current_date: str = dspy.InputField(
        desc="Сегодняшняя дата в формате 'ДД месяц' и день недели "
        "(например: 11 августа, вторник)"
    )
    current_year: str = dspy.InputField(
        desc="Текущий год, например 2026"
    )

    title: Optional[str] = dspy.OutputField(
        desc="Краткое название события или null, если события нет"
    )
    date: Optional[str] = dspy.OutputField(
        desc="Дата и время начала в формате YYYY-MM-DD HH:MM или null"
    )
    end_date: Optional[str] = dspy.OutputField(
        desc="Дата и время окончания в формате YYYY-MM-DD HH:MM или null"
    )
    location: Optional[str] = dspy.OutputField(
        desc="Место: конкретный адрес, заведение или точка сбора/отправления, "
        "если указана; иначе город или район. null, если неизвестно"
    )
    description: Optional[str] = dspy.OutputField(
        desc="Краткое описание события или null"
    )
    tags: Optional[list[str]] = dspy.OutputField(
        desc="Массив ключевых слов или null"
    )
    category: Optional[Category] = dspy.OutputField(
        desc="музыка/спорт/образование/другое или null"
    )
    price: Optional[str] = dspy.OutputField(
        desc="бесплатно/1000₽/от 500₽ или null"
    )
    event_type: Optional[EventType] = dspy.OutputField(
        desc="онлайн/офлайн/гибрид"
    )
    image_url: Optional[str] = dspy.OutputField(
        desc="Ссылка на картинку или null"
    )
    external_url: Optional[str] = dspy.OutputField(
        desc="Внешняя ссылка или null"
    )


class LLMError(Exception):
    """Raised when the LLM request itself fails (quota, network, ...)."""


class EventExtractor:
    """Extracts event data from a message text via a DSPy program."""

    def __init__(self):
        self.lm = dspy.LM(
            model=f"openai/{config.LLM_MODEL}",
            api_key=config.LLM_API_KEY,
            api_base=config.LLM_BASE_URL,
            temperature=0,
            cache=False,
        )
        dspy.configure(lm=self.lm)
        self.program = dspy.Predict(EventSignature)

        compiled = os.getenv("COMPILED_PROGRAM_PATH")
        if compiled and os.path.exists(compiled):
            try:
                self.program.load(compiled)
                print(f"✅ Loaded compiled DSPy program from {compiled}")
            except Exception as exc:
                print(f"⚠️ Could not load compiled program: {exc}")

    def extract(self, text: str, current_date: datetime) -> dict | None:
        """Send text to the DSPy program and return the extracted event.

        Returns None when the message legitimately has no event.
        Raises LLMError when the LLM request itself fails.
        """
        now = current_date or datetime.now()
        try:
            result = self.program(
                text=text,
                current_date=(
                    f"{now.day} {MONTHS[now.month - 1]}, "
                    f"{WEEKDAYS[now.weekday()]}"
                ),
                current_year=str(now.year),
            )
        except Exception as exc:
            print(f"❌ DSPy program call failed: {exc}")
            raise LLMError(str(exc)) from exc

        payload = {
            "title": result.title,
            "location": result.location,
            "description": result.description,
            "tags": result.tags,
            "category": result.category,
            "price": result.price,
            "event_type": result.event_type,
            "image_url": result.image_url,
            "external_url": result.external_url,
        }

        if not result.date:
            print("ℹ️ No date found in message")
            return None

        event_date = _parse_datetime(result.date)
        if not event_date:
            print(f"⚠️ Could not parse event date: {result.date!r}")
            return None
        payload["event_date"] = event_date

        if result.end_date:
            payload["end_date"] = _parse_datetime(result.end_date)

        print("✅ Event extracted via DSPy")
        return payload


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
