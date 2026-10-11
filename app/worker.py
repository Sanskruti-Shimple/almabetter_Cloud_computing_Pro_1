import json
import logging
import signal
import time

from confluent_kafka import Consumer
from redis import Redis

from app.broker import EventPublisher, ensure_topic, kafka_config
from app.config import get_settings
from app.models import MusicEvent
from app.processor import process_event

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)
stopping = False


def request_shutdown(_signal, _frame):
    global stopping
    stopping = True


def run() -> None:
    settings = get_settings()
    ensure_topic(settings)
    consumer = Consumer(
        {
            **kafka_config(settings, client_id="streamify-worker"),
            "group.id": settings.kafka_group_id,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    dead_letter = EventPublisher(settings)
    consumer.subscribe([settings.kafka_topic])
    attempts = {}
    logger.info("Worker subscribed to %s", settings.kafka_topic)
    try:
        while not stopping:
            message = consumer.poll(1.0)
            if message is None:
                continue
            if message.error():
                logger.error("Kafka consumer error: %s", message.error())
                continue
            key = (message.topic(), message.partition(), message.offset())
            try:
                event = MusicEvent.model_validate_json(message.value() or b"")
                changed = process_event(event, redis, settings)
                consumer.commit(message=message, asynchronous=False)
                attempts.pop(key, None)
                logger.info("Processed event %s (new=%s)", event.event_id, changed)
            except Exception as error:
                count = attempts.get(key, 0) + 1
                attempts[key] = count
                logger.exception("Event processing failed on attempt %s: %s", count, error)
                if count >= settings.consumer_max_retries:
                    dead_letter.publish_and_wait(
                        settings.kafka_dlq_topic,
                        f"{message.topic()}:{message.partition()}:{message.offset()}",
                        json.dumps(
                            {
                                "source_topic": message.topic(),
                                "partition": message.partition(),
                                "offset": message.offset(),
                                "error": str(error)[:1000],
                                "payload": (message.value() or b"").decode("utf-8", errors="replace"),
                            }
                        ).encode(),
                    )
                    consumer.commit(message=message, asynchronous=False)
                    attempts.pop(key, None)
                    logger.error("Sent event to dead-letter topic after %s attempts", count)
                else:
                    time.sleep(min(2**count, 8))
    finally:
        consumer.close()
        dead_letter.close()
        redis.close()


if __name__ == "__main__":
    signal.signal(signal.SIGINT, request_shutdown)
    signal.signal(signal.SIGTERM, request_shutdown)
    run()
