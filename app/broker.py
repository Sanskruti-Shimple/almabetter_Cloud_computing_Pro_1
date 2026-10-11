from confluent_kafka import KafkaException, Producer
from confluent_kafka.admin import AdminClient, NewTopic
from azure.identity import DefaultAzureCredential

from app.config import Settings


def _oauth_callback(settings: Settings):
    credential = DefaultAzureCredential()

    def issue_token(_config):
        namespace_fqdn = f"{settings.eventhub_namespace}.servicebus.windows.net"
        token = credential.get_token(f"https://{namespace_fqdn}/.default")
        return token.token, token.expires_on

    return issue_token


def kafka_config(settings: Settings, *, client_id: str) -> dict:
    config = {
        "bootstrap.servers": settings.kafka_bootstrap_servers,
        "client.id": client_id,
        "security.protocol": settings.kafka_security_protocol,
    }
    if settings.eventhub_namespace:
        config.update(
            {
                "bootstrap.servers": f"{settings.eventhub_namespace}.servicebus.windows.net:9093",
                "security.protocol": "SASL_SSL",
                "sasl.mechanism": "OAUTHBEARER",
                "oauth_cb": _oauth_callback(settings),
            }
        )
    return config


def producer_config(settings: Settings, *, client_id: str) -> dict:
    return {
        **kafka_config(settings, client_id=client_id),
        "acks": "all",
        "enable.idempotence": not bool(settings.eventhub_namespace),
        "message.timeout.ms": 10000,
    }


class EventPublisher:
    def __init__(self, settings: Settings):
        self._producer = Producer(producer_config(settings, client_id="streamify-api"))

    def publish(self, topic: str, key: str, value: bytes) -> None:
        self.publish_and_wait(topic, key, value)

    def publish_and_wait(self, topic: str, key: str, value: bytes) -> None:
        delivered = []

        def on_delivery(error, _message):
            delivered.append(error)

        self._producer.produce(topic, key=key.encode(), value=value, callback=on_delivery)
        remaining = self._producer.flush(10)
        if remaining:
            raise TimeoutError("Kafka delivery did not complete before timeout")
        if not delivered:
            raise TimeoutError("Kafka producer returned without a delivery result")
        if delivered[0] is not None:
            raise KafkaException(delivered[0])

    def ready(self, topic: str) -> None:
        self._producer.list_topics(topic=topic, timeout=3)

    def close(self) -> None:
        self._producer.flush(5)


def ensure_topic(settings: Settings) -> None:
    if settings.eventhub_namespace:
        return
    client = AdminClient(kafka_config(settings, client_id="streamify-topic-init"))
    topics = [
        NewTopic(
            settings.kafka_topic,
            num_partitions=6,
            replication_factor=1,
            config={"retention.ms": "604800000"},
        ),
        NewTopic(
            settings.kafka_dlq_topic,
            num_partitions=3,
            replication_factor=1,
            config={"retention.ms": "604800000"},
        ),
    ]
    futures = client.create_topics(topics, request_timeout=10)
    for future in futures.values():
        try:
            future.result()
        except Exception as error:
            if "TOPIC_ALREADY_EXISTS" not in str(error):
                raise
