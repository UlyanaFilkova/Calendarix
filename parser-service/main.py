"""Parser Service entry point: RabbitMQ worker that scans channels."""

import json
import time
from datetime import datetime, timezone

import pika

import config
from services.telegram_reader import TelegramReader

PARSE_REQUESTS_QUEUE = "parse_requests"
PARSE_RESULTS_QUEUE = "parse_results"

RECONNECT_DELAY = 5  # seconds between reconnect attempts

reader = TelegramReader()


def _connect() -> tuple:
    """Open a RabbitMQ connection with heartbeats disabled.

    A single scan can take minutes (LLM calls per post), so a fixed
    60s heartbeat would kill the connection mid-task.
    """
    params = pika.URLParameters(config.RABBITMQ_URL)
    params.heartbeat = 0
    connection = pika.BlockingConnection(params)
    channel = connection.channel()
    channel.queue_declare(queue=PARSE_REQUESTS_QUEUE, durable=True)
    channel.queue_declare(queue=PARSE_RESULTS_QUEUE, durable=True)
    channel.basic_qos(prefetch_count=1)
    return connection, channel


def on_parse_request(ch, method, properties, body):
    """Handle one task from the parse_requests queue."""
    try:
        request = json.loads(body.decode("utf-8"))
        source_id = request.get("source_id")
        user_id = request.get("user_id")
        url = request.get("url", "")
        print(f"📥 Task received: source_id={source_id}, url={url}")

        events, checked = reader.scan_channel(url)

        response = {
            "source_id": source_id,
            "user_id": user_id,
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
        try:
            ch.basic_nack(
                delivery_tag=method.delivery_tag, requeue=True
            )
        except Exception:
            pass


def main() -> None:
    """Start the RabbitMQ consumer and keep it running with reconnects."""
    while True:
        connection = None
        try:
            connection, channel = _connect()
            channel.basic_consume(
                queue=PARSE_REQUESTS_QUEUE,
                on_message_callback=on_parse_request,
            )
            print("🔍 Parser is ready. Waiting for tasks...")
            channel.start_consuming()
        except KeyboardInterrupt:
            print("👋 Parser stopped by user (Ctrl+C)")
            break
        except Exception as exc:
            print(f"❌ Parser error: {exc}")
        finally:
            if connection and connection.is_open:
                try:
                    connection.close()
                except Exception:
                    pass
        print(f"🔄 Reconnecting in {RECONNECT_DELAY}s...")
        time.sleep(RECONNECT_DELAY)


if __name__ == "__main__":
    main()
