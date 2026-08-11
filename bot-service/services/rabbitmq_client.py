"""RabbitMQ client for exchanging messages between services.

pika's BlockingConnection is not thread-safe: the consumer runs in a
background thread while the publisher is called from the bot's main
thread. Sharing one connection between threads corrupts the AMQP stream,
so we keep two separate connections — one for publishing, one for
consuming — each used by a single thread.
"""

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
        self._publisher_conn = None
        self._publisher_channel = None
        self._consumer_conn = None
        self._consumer_channel = None
        self._publisher_lock = threading.RLock()
        self._consumer_lock = threading.RLock()

    def _open(self) -> tuple:
        """Open a connection and declare durable queues.

        Heartbeats are disabled: the publisher connection is owned by the
        bot's main thread, which is blocked in the Telegram polling loop
        and never processes pika I/O between sends, so RabbitMQ would
        close it as unresponsive after the heartbeat timeout.
        """
        params = pika.URLParameters(self.url)
        params.heartbeat = 0
        connection = pika.BlockingConnection(params)
        channel = connection.channel()
        channel.queue_declare(queue=PARSE_REQUESTS_QUEUE, durable=True)
        channel.queue_declare(queue=PARSE_RESULTS_QUEUE, durable=True)
        return connection, channel

    def connect(self) -> None:
        """Initial connection (publisher side)."""
        with self._publisher_lock:
            self._publisher_conn, self._publisher_channel = self._open()
            print("✅ Connected to RabbitMQ")

    def _ensure_publisher(self) -> None:
        """Reconnect the publisher connection if it is dead."""
        with self._publisher_lock:
            closed = (
                not self._publisher_conn
                or not self._publisher_conn.is_open
                or not self._publisher_channel
                or not self._publisher_channel.is_open
            )
            if closed:
                print("🔄 Reconnecting publisher to RabbitMQ...")
                try:
                    self._close_publisher()
                except Exception:
                    pass
                self._publisher_conn, self._publisher_channel = self._open()

    def _ensure_consumer(self) -> None:
        """Reconnect the consumer connection if it is dead."""
        with self._consumer_lock:
            closed = (
                not self._consumer_conn
                or not self._consumer_conn.is_open
                or not self._consumer_channel
                or not self._consumer_channel.is_open
            )
            if closed:
                print("🔄 Reconnecting consumer to RabbitMQ...")
                try:
                    self._close_consumer()
                except Exception:
                    pass
                self._consumer_conn, self._consumer_channel = self._open()

    def send_parse_request(
        self, source_id: int, url: str, user_id: int
    ) -> bool:
        """Publish a parsing task to the parse_requests queue."""
        try:
            self._ensure_publisher()
            message = json.dumps(
                {
                    "source_id": source_id,
                    "url": url,
                    "user_id": user_id,
                },
                ensure_ascii=False,
            )
            self._publisher_channel.basic_publish(
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
            self._close_publisher()
            return False

    def start_consuming(self, callback_function) -> None:
        """Start listening for parse results in a background thread."""
        def _consume() -> None:
            while True:
                try:
                    self._ensure_consumer()
                    for method, properties, body in self._consumer_channel.consume(
                        queue=PARSE_RESULTS_QUEUE, auto_ack=False
                    ):
                        try:
                            data = json.loads(body.decode("utf-8"))
                            callback_function(data)
                            self._consumer_channel.basic_ack(
                                delivery_tag=method.delivery_tag
                            )
                        except Exception as exc:
                            print(f"❌ Failed to process parse result: {exc}")
                            self._consumer_channel.basic_nack(
                                delivery_tag=method.delivery_tag,
                                requeue=False,
                            )
                except Exception as exc:
                    print(f"⚠️ Consumer lost connection: {exc}")
                    print(f"🔄 Will retry in {RECONNECT_DELAY}s...")
                    self._close_consumer()
                    time.sleep(RECONNECT_DELAY)

        thread = threading.Thread(target=_consume, daemon=True)
        thread.start()
        print("🔄 Listening for parse results...")

    def _close_publisher(self) -> None:
        """Close the publisher connection."""
        try:
            with self._publisher_lock:
                if (
                    self._publisher_conn
                    and self._publisher_conn.is_open
                ):
                    self._publisher_conn.close()
        except Exception:
            pass
        finally:
            self._publisher_conn = None
            self._publisher_channel = None

    def _close_consumer(self) -> None:
        """Close the consumer connection."""
        try:
            with self._consumer_lock:
                if self._consumer_conn and self._consumer_conn.is_open:
                    self._consumer_conn.close()
        except Exception:
            pass
        finally:
            self._consumer_conn = None
            self._consumer_channel = None

    def close(self) -> None:
        """Close both RabbitMQ connections."""
        self._close_publisher()
        self._close_consumer()
        print("👋 RabbitMQ connections closed")
