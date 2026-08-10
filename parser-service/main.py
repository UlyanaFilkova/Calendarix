"""Parser Service entry point: RabbitMQ worker that scans channels."""

import asyncio
import json
import threading
from datetime import datetime, timezone

import pika

import config
from services.telegram_reader import TelegramReader

PARSE_REQUESTS_QUEUE = "parse_requests"
PARSE_RESULTS_QUEUE = "parse_results"

reader = TelegramReader()

# Persistent event loop for the Telethon client
_loop = asyncio.new_event_loop()
_loop.run_until_complete(reader.connect())
_thread = threading.Thread(target=_loop.run_forever, daemon=True)
_thread.start()


def on_parse_request(ch, method, properties, body):
    """Handle one task from the parse_requests queue."""
    try:
        request = json.loads(body.decode("utf-8"))
        source_id = request.get("source_id")
        url = request.get("url", "")
        print(f"📥 Task received: source_id={source_id}, url={url}")

        future = asyncio.run_coroutine_threadsafe(
            reader.scan_channel(url), _loop
        )
        events, checked = future.result(timeout=120)

        response = {
            "source_id": source_id,
            "events": events,
            "scanned_at": datetime.now(timezone.utc).isoformat(),
        }
        ch.basic_publish(
            exchange="",
            routing_key=PARSE_RESULTS_QUEUE,
            body=json.dumps(response, ensure_ascii=False, default=str),
            properties=pika.BasicProperties(delivery_mode=2),
        )
        print(
            f"📤 Result sent: events={len(events)}, "
            f"checked={checked} messages"
        )
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as exc:
        print(f"❌ Task failed: {exc}")
        ch.basic_nack(
            delivery_tag=method.delivery_tag, requeue=True
        )


def main() -> None:
    """Start the RabbitMQ consumer and keep it running."""
    connection = None
    try:
        connection = pika.BlockingConnection(
            pika.URLParameters(config.RABBITMQ_URL)
        )
        channel = connection.channel()
        channel.queue_declare(queue=PARSE_REQUESTS_QUEUE, durable=True)
        channel.queue_declare(queue=PARSE_RESULTS_QUEUE, durable=True)
        channel.basic_qos(prefetch_count=1)

        channel.basic_consume(
            queue=PARSE_REQUESTS_QUEUE, on_message_callback=on_parse_request
        )
        print("🔍 Parser is ready. Waiting for tasks...")
        channel.start_consuming()
    except KeyboardInterrupt:
        print("👋 Parser stopped by user (Ctrl+C)")
    except Exception as exc:
        print(f"❌ Parser error: {exc}")
    finally:
        if connection and connection.is_open:
            connection.close()
            print("👋 RabbitMQ connection closed")


if __name__ == "__main__":
    main()
