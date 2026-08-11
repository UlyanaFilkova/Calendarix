"""Train / optimize the DSPy event-extraction program.

Reads real events (original_text + extracted fields) from Postgres,
compiles the DSPy program with few-shot demos, and saves it to
/app/data/compiled_program.json so the parser loads it at startup.

Run from the parser container:
    docker exec calendarix-parser python optimize.py
"""

import os
from datetime import datetime
from typing import Optional

import dspy
import psycopg2
from dotenv import load_dotenv

import config
from services.nlp import Category, EventSignature, EventType, MONTHS, WEEKDAYS

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://calendarix:password@postgres:5432/calendarix",
)
COMPILED_PROGRAM_PATH = os.getenv(
    "COMPILED_PROGRAM_PATH",
    "/app/data/compiled_program.json",
)

KNOWN_CATEGORIES = {"музыка", "спорт", "образование", "другое"}


def _load_events() -> list[dict]:
    """Fetch stored events with original text from Postgres."""
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT original_text, title,
                       to_char(event_date, 'YYYY-MM-DD HH24:MI') AS date,
                       COALESCE(to_char(end_date, 'YYYY-MM-DD HH24:MI'), '')
                          AS end_date,
                       COALESCE(location, '') AS location,
                       COALESCE(description, '') AS description,
                       COALESCE(tags, '') AS tags,
                       COALESCE(category, '') AS category,
                       COALESCE(price, '') AS price
                FROM events
                WHERE original_text IS NOT NULL
                  AND original_text != ''
                  AND title IS NOT NULL
                ORDER BY id
                """
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    events = []
    for (
        text, title, date, end_date, location, description,
        tags, category, price,
    ) in rows:
        if not text.strip() or not title.strip() or not date.strip():
            continue
        events.append({
            "text": text,
            "title": title,
            "date": date,
            "end_date": end_date or None,
            "location": location or None,
            "description": description or None,
            "tags": _parse_tags(tags),
            "category": category if category in KNOWN_CATEGORIES else None,
            "price": price or None,
        })
    return events


def _parse_tags(raw: str) -> list[str] | None:
    """Parse a Postgres text[] literal like {a,b,\"c d\"} into a list."""
    if not raw or raw == "{}":
        return None
    items = []
    current = []
    in_quotes = False
    i = 0
    s = raw[1:-1]  # strip braces
    while i < len(s):
        ch = s[i]
        if ch == "\\" and i + 1 < len(s):
            current.append(s[i + 1])
            i += 2
            continue
        if ch == '"':
            in_quotes = not in_quotes
        elif ch == "," and not in_quotes:
            items.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
        i += 1
    if current:
        items.append("".join(current).strip())
    return [it for it in items if it] or None


def _build_examples(events: list[dict], dev_count: int) -> tuple[list, list]:
    """Split events into DSPy trainset and devset.

    The current_date passed to the model is derived from the event date,
    so relative references (завтра, в субботу) stay resolvable.
    """
    trainset = []
    for ev in events:
        date = datetime.strptime(ev["date"], "%Y-%m-%d %H:%M")
        current_date = (
            f"{date.day} {MONTHS[date.month - 1]}, "
            f"{WEEKDAYS[date.weekday()]}"
        )
        trainset.append(
            dspy.Example(
                text=ev["text"],
                current_date=current_date,
                current_year=str(date.year),
                title=ev["title"],
                date=ev["date"],
                end_date=ev["end_date"],
                location=ev["location"],
                description=ev["description"],
                tags=ev["tags"],
                category=ev["category"],
                price=ev["price"],
                event_type=None,
                image_url=None,
                external_url=None,
            ).with_inputs("text", "current_date", "current_year")
        )
    devset = trainset[:dev_count]
    trainset = trainset[dev_count:]
    return trainset, devset


def _normalize(value: str | None) -> str:
    return " ".join((value or "").lower().split())


def metric(gold, pred, trace=None) -> float:
    """Score one prediction against the gold example (0..1)."""
    scores = []
    checks = {
        "title": _normalize(gold.title) == _normalize(pred.title or ""),
        "date": _normalize(gold.date) == _normalize(pred.date or ""),
        "location": _normalize(gold.location) == _normalize(pred.location or ""),
        "price": _normalize(gold.price) == _normalize(pred.price or ""),
        "category": _normalize(gold.category) == _normalize(pred.category or ""),
    }
    if gold.tags or pred.tags:
        gold_tags = {t.lower() for t in (gold.tags or [])}
        pred_tags = {t.lower() for t in (pred.tags or [])}
        if gold_tags:
            checks["tags"] = len(gold_tags & pred_tags) / len(gold_tags)
        else:
            checks["tags"] = 1.0 if not pred_tags else 0.0
    for key, ok in checks.items():
        scores.append(1.0 if ok else 0.0)
    return sum(scores) / len(scores)


def main() -> None:
    """Load real events, compile the program, save it."""
    lm = dspy.LM(
        model=f"openai/{config.LLM_MODEL}",
        api_key=config.LLM_API_KEY,
        api_base=config.LLM_BASE_URL,
        temperature=0,
    )
    dspy.configure(lm=lm)

    events = _load_events()
    print(f"📊 Loaded {len(events)} events from the database")
    if not events:
        raise SystemExit("No training data found. Add channels and rescan first.")

    trainset, devset = _build_examples(events, dev_count=2)
    print(f"🧪 trainset={len(trainset)}, devset={len(devset)}")

    teacher = dspy.Predict(EventSignature)
    teleprompter = dspy.BootstrapFewShot(
        metric=metric,
        max_bootstrapped_demos=4,
        max_labeled_demos=8,
    )
    compiled = teleprompter.compile(teacher, trainset=trainset)
    print("✅ Program compiled")

    compiled.save(COMPILED_PROGRAM_PATH)
    print(f"💾 Saved compiled program to {COMPILED_PROGRAM_PATH}")

    evaluate = dspy.Evaluate(
        devset=devset, metric=metric, num_threads=1, display_progress=False
    )
    score = evaluate(compiled)
    print(f"📈 Dev score: {score}")


if __name__ == "__main__":
    main()
