"""RabbitMQ client for exchanging messages between services."""

import json
import threading

import pika

PARSE_REQUESTS_QUEUE = "parse_requests"
PARSE_RESULTS_QUEUE = "parse_results"


class RabbitMQClient:
    """Publisher of parse requests and consumer of parse results."""

    def __init__(self, url: str):
        self.url = url
        self.connection = None
        self.channel = None

    def connect(self) -> None:
        """Connect to RabbitMQ and declare durable queues."""
        try:
            self.connection = pika.BlockingConnection(
                pika.URLParameters(self.url)
            )
            self.channel = self.connection.channel()
            self.channel.queue_declare(
                queue=PARSE_REQUESTS_QUEUE, durable=True
            )
            self.channel.queue_declare(
                queue=PARSE_RESULTS_QUEUE, durable=True
            )
            print("✅ Connected to RabbitMQ")
        except Exception as exc:
            print(f"❌ Failed to connect to RabbitMQ: {exc}")
            raise

    def send_parse_request(
        self, source_id: int, url: str, user_id: int
    ) -> None:
        """Publish a parsing task to the parse_requests queue."""
        try:
            message = json.dumps(
                {
                    "source_id": source_id,
                    "url": url,
                    "user_id": user_id,
                },
                ensure_ascii=False,
            )
            self.channel.basic_publish(
                exchange="",
                routing_key=PARSE_REQUESTS_QUEUE,
                body=message,
                properties=pika.BasicProperties(
                    delivery_mode=2,  # persistent message
                ),
            )
            print(
                f"📤 Parse request sent for source {source_id} "
                f"(user {user_id})"
            )
        except Exception as exc:
            print(f"❌ Failed to send parse request: {exc}")

    def start_consuming(self, callback_function) -> None:
        """Start listening for parse results in a background thread."""
        def _consume() -> None:
            try:
                for method, properties, body in self.channel.consume(
                    queue=PARSE_RESULTS_QUEUE, auto_ack=False
                ):
                    try:
                        data = json.loads(body.decode("utf-8"))
                        callback_function(data)
                        self.channel.basic_ack(
                            delivery_tag=method.delivery_tag
                        )
                    except Exception as exc:
                        print(f"❌ Failed to process parse result: {exc}")
                        self.channel.basic_nack(
                            delivery_tag=method.delivery_tag,
                            requeue=False,
                        )
            except Exception as exc:
                print(f"❌ Consumer stopped: {exc}")

        thread = threading.Thread(target=_consume, daemon=True)
        thread.start()
        print("🔄 Listening for parse results...")

    def close(self) -> None:
        """Close the RabbitMQ connection."""
        try:
            if self.connection and self.connection.is_open:
                self.connection.close()
                print("👋 RabbitMQ connection closed")
        except Exception as exc:
            print(f"❌ Failed to close RabbitMQ connection: {exc}")
