from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
import app.broker as broker
from app.models import EventRequest, EventType, MusicEvent
from app.processor import process_event
from app.security import pseudonymize_user_id
import app.main as main


def test_event_request_rejects_unexpected_fields_and_unsafe_identifiers():
    with pytest.raises(ValidationError):
        EventRequest(event_type="play", user_id="user@example.com", track_id="track-1")
    with pytest.raises(ValidationError):
        EventRequest(event_type="play", user_id="user-1", track_id="track-1", email="private")


def test_user_identifier_is_stable_and_keyed():
    settings = Settings(
        service_role="worker",
        pii_hmac_key="a" * 40,
    )
    first = pseudonymize_user_id("student-user", settings)
    assert first == pseudonymize_user_id("student-user", settings)
    assert first != pseudonymize_user_id("different-user", settings)
    assert len(first) == 64


def test_production_settings_reject_placeholders_and_separate_worker_secrets():
    with pytest.raises(ValidationError):
        Settings(
            app_env="production",
            eventhub_namespace="events",
            azure_storage_account_url="https://storage.blob.core.windows.net",
            pii_hmac_key="replace-with-a-random-secret-of-at-least-32-characters",
            api_read_token="r" * 40,
            api_write_token="w" * 40,
        )

    worker_settings = Settings(
        app_env="production",
        service_role="worker",
        eventhub_namespace="events",
        azure_storage_account_url="https://storage.blob.core.windows.net",
        pii_hmac_key="p" * 40,
    )
    assert worker_settings.service_role == "worker"


def test_processor_archives_and_applies_idempotency(monkeypatch):
    settings = Settings(service_role="worker", pii_hmac_key="b" * 40)
    archived = []
    monkeypatch.setattr("app.processor.archive_event", lambda event, _settings: archived.append(event.event_id))

    class FakeRedis:
        def __init__(self):
            self.seen = set()
            self.increments = []

        def eval(self, _script, _count, event_key, _rank_key, _ttl, score, track_id):
            if event_key in self.seen:
                return 0
            self.seen.add(event_key)
            self.increments.append((score, track_id))
            return 1

    redis = FakeRedis()
    event = MusicEvent(
        event_id=uuid4(),
        event_type=EventType.play,
        user_id="pseudonym",
        track_id="track-1",
        occurred_at=datetime.now(timezone.utc),
    )
    assert process_event(event, redis, settings) is True
    assert process_event(event, redis, settings) is False
    assert len(archived) == 2
    assert redis.increments == [(1, "track-1"), (1, "track-1")]


def test_ingestion_returns_accepted_only_after_publishing_and_pseudonymizes(monkeypatch):
    settings = Settings(
        api_read_token="r" * 40,
        api_write_token="w" * 40,
        pii_hmac_key="c" * 40,
    )

    class FakeRedis:
        def ping(self):
            return True

        def close(self):
            pass

    class FakePublisher:
        messages = []

        def __init__(self, _settings):
            pass

        def publish(self, topic, key, value):
            self.messages.append((topic, key, value))

        def close(self):
            pass

    monkeypatch.setattr(main, "get_settings", lambda: settings)
    monkeypatch.setattr(main, "EventPublisher", FakePublisher)
    monkeypatch.setattr(main.Redis, "from_url", lambda *_args, **_kwargs: FakeRedis())

    with TestClient(main.app) as client:
        response = client.post(
            "/v1/events",
            json={"event_type": "play", "user_id": "student-user", "track_id": "track-9"},
            headers={"Authorization": "Bearer " + settings.api_write_token.get_secret_value()},
        )

    assert response.status_code == 202
    message = FakePublisher.messages[-1]
    assert message[0] == settings.kafka_topic
    assert message[1] == response.json()["event_id"]
    published = MusicEvent.model_validate_json(message[2])
    assert published.user_id == pseudonymize_user_id("student-user", settings)
    assert "student-user" not in message[2].decode()


def test_recommendations_exclude_user_history(monkeypatch):
    settings = Settings(
        api_read_token="r" * 40,
        api_write_token="w" * 40,
        pii_hmac_key="d" * 40,
    )

    class FakeRedis:
        def ping(self):
            return True

        def close(self):
            pass

        def zrevrange(self, key, _start, _stop):
            if key.startswith("user:"):
                return ["already-played"]
            return ["already-played", "recommended"]

    monkeypatch.setattr(main, "get_settings", lambda: settings)
    monkeypatch.setattr(main, "EventPublisher", lambda _settings: type("Publisher", (), {"close": lambda self: None})())
    monkeypatch.setattr(main.Redis, "from_url", lambda *_args, **_kwargs: FakeRedis())

    with TestClient(main.app) as client:
        response = client.get(
            "/v1/recommendations",
            params={"user_id": "student-user"},
            headers={"Authorization": "Bearer " + settings.api_read_token.get_secret_value()},
        )

    assert response.status_code == 200
    assert response.json()["track_ids"] == ["recommended"]
    assert response.json()["user_id"] == pseudonymize_user_id("student-user", settings)[:12]


def test_endpoint_scope_is_enforced(monkeypatch):
    settings = Settings(
        api_read_token="r" * 40,
        api_write_token="w" * 40,
        pii_hmac_key="e" * 40,
    )

    class FakeRedis:
        def close(self):
            pass

    monkeypatch.setattr(main, "get_settings", lambda: settings)
    monkeypatch.setattr(main, "EventPublisher", lambda _settings: type("Publisher", (), {"close": lambda self: None})())
    monkeypatch.setattr(main.Redis, "from_url", lambda *_args, **_kwargs: FakeRedis())

    with TestClient(main.app) as client:
        unauthenticated = client.post(
            "/v1/events",
            json={"event_type": "play", "user_id": "student-user", "track_id": "track-9"},
        )
        wrong_scope = client.post(
            "/v1/events",
            json={"event_type": "play", "user_id": "student-user", "track_id": "track-9"},
            headers={"Authorization": "Bearer " + settings.api_read_token.get_secret_value()},
        )

    assert unauthenticated.status_code == 401
    assert wrong_scope.status_code == 403


def test_eventhub_oauth_uses_namespace_specific_scope(monkeypatch):
    requested_scopes = []

    class FakeCredential:
        def get_token(self, scope):
            requested_scopes.append(scope)
            return type("Token", (), {"token": "access-token", "expires_on": 123.0})()

    monkeypatch.setattr(broker, "DefaultAzureCredential", FakeCredential)
    settings = Settings(
        service_role="worker",
        eventhub_namespace="events",
        pii_hmac_key="p" * 40,
    )

    token, expires_on = broker.kafka_config(settings, client_id="test")["oauth_cb"](None)

    assert requested_scopes == ["https://events.servicebus.windows.net/.default"]
    assert (token, expires_on) == ("access-token", 123.0)
