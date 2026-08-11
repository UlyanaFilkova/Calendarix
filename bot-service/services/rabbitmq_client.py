"""RabbitMQ client for exchanging messages between services."""

import json
import threading
import time

import pika

PARSE_REQUESTS_QUEUE = "parse_requests"
PARSE_RESULTS_QUEUE = "parse_results"

RECONNECT_DELAY = 5  # seconds between reconnect attempts


class RabbitMQClient:
    """Publisher of parse requests and consumer of parse results."""

    def __init__(self, url: str):
        self.url = url
        self.connection = None
        self.channel = None
        self._lock = threading.Lock()

    def _connect(self) -> None:
        """Open a connection and declare durable queues."""
        with self._lock:
            self.connection = pika.BlockingConnection(
                pika.URLParameters(self.url),
            )
            self.channel = self.connection.channel()
            self.channel.queue_declare(
                queue=PARSE_REQUESTS_QUEUE, durable=True
            )
            self.channel.queue_declare(
                queue=PARSE_RESULTS_QUEUE, durable=True
            )
            print("✅ Connected to RabbitMQ")

    def connect(self) -> None:
        """Initial connection to RabbitMQ."""
        self._connect()

    def _ensure_connection(self) -> None:
        """Reconnect if the connection or channel is dead."""
        closed = (
            not self.connection
            or not self.connection.is_open
            or not self.channel
            or not self.channel.is_open
        )
        if closed:
            print("🔄 Reconnecting to RabbitMQ...")
            try:
                self.close()
            except Exception:
                pass
            self._connect()

    def send_parse_request(
        self, source_id: int, url: str, user_id: int
    ) -> bool:
        """Publish a parsing task to the parse_requests queue."""
        try:
            self._ensure_connection()
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
            return True
        except Exception as exc:
            print(f"❌ Failed to send parse request: {exc}")
            return False

    def start_consuming(self, callback_function) -> None:
        """Start listening for parse results in a background thread."""
        def _consume() -> None:
            while True:
                try:
                    self._ensure_connection()
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
                    print(f"⚠️ Consumer lost connection: {exc}")
                    print(f"🔄 Will retry in {RECONNECT_DELAY}s...")
                    time.sleep(RECONNECT_DELAY)

        thread = threading.Thread(target=_consume, daemon=True)
        thread.start()
        print("🔄 Listening for parse results...")

    def close(self) -> None:
        """Close the RabbitMQ connection."""
        try:
            with self._lock:
                if self.connection and self.connection.is_open:
                    self.connection.close()
                    print("👋 RabbitMQ connection closed")
        except Exception as exc:
            print(f"❌ Failed to close RabbitMQ connection: {exc}")
