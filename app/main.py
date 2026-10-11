import logging
import hmac
from contextlib import asynccontextmanager
from confluent_kafka import KafkaException
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from redis import Redis

from app.broker import EventPublisher
from app.config import get_settings
from app.models import EventAccepted, EventRequest, MusicEvent, RecommendationResponse
from app.security import pseudonymize_user_id

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer(auto_error=False)

EVENTS_ACCEPTED = Counter("streamify_events_accepted_total", "Accepted music events")
EVENTS_FAILED = Counter("streamify_events_failed_total", "Event publishing failures")
HTTP_LATENCY = Histogram("streamify_http_request_seconds", "HTTP request latency", ["route"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.settings = settings
    app.state.redis = Redis.from_url(settings.redis_url, decode_responses=True)
    app.state.publisher = EventPublisher(settings)
    try:
        yield
    finally:
        app.state.publisher.close()
        app.state.redis.close()


app = FastAPI(
    title="Streamify Music Events API",
    version="1.0.0",
    description="Educational real-time music interaction event prototype.",
    lifespan=lifespan,
)


def require_scope(scope: str):
    def verify(
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    ) -> str:
        if credentials is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Bearer credentials required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        settings = request.app.state.settings
        supplied = credentials.credentials
        scoped_token = getattr(settings, f"api_{scope}_token").get_secret_value()
        read_token = settings.api_read_token.get_secret_value()
        write_token = settings.api_write_token.get_secret_value()
        supplied_bytes = supplied.encode("utf-8")
        if hmac.compare_digest(supplied_bytes, scoped_token.encode("utf-8")):
            return scope
        if hmac.compare_digest(supplied_bytes, read_token.encode("utf-8")) or hmac.compare_digest(
            supplied_bytes, write_token.encode("utf-8")
        ):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bearer token lacks required scope")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return verify


@app.middleware("http")
async def measure_request(request: Request, call_next):
    route = request.url.path
    with HTTP_LATENCY.labels(route=route).time():
        return await call_next(request)


@app.get("/health/live", tags=["health"])
def liveness():
    return {"status": "alive"}


@app.get("/health/ready", tags=["health"])
def readiness(request: Request):
    try:
        request.app.state.redis.ping()
        request.app.state.publisher.ready(request.app.state.settings.kafka_topic)
    except Exception as error:
        logger.warning("Readiness check failed: %s", error)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Dependencies unavailable")
    return {"status": "ready"}


@app.post("/v1/events", response_model=EventAccepted, status_code=status.HTTP_202_ACCEPTED)
def ingest_event(
    payload: EventRequest,
    request: Request,
    _scope: str = Depends(require_scope("write")),
):
    settings = request.app.state.settings
    event = MusicEvent(
        event_type=payload.event_type,
        user_id=pseudonymize_user_id(payload.user_id, settings),
        track_id=payload.track_id,
    )
    try:
        request.app.state.publisher.publish(
            settings.kafka_topic,
            str(event.event_id),
            event.model_dump_json().encode("utf-8"),
        )
    except (KafkaException, BufferError, TimeoutError) as error:
        EVENTS_FAILED.inc()
        logger.error("Failed to enqueue event %s: %s", event.event_id, error)
        raise HTTPException(status_code=503, detail="Event stream temporarily unavailable")
    EVENTS_ACCEPTED.inc()
    return EventAccepted(event_id=event.event_id)


@app.get("/v1/recommendations", response_model=RecommendationResponse)
def recommendations(
    request: Request,
    user_id: str = Query(min_length=1, max_length=128),
    _scope: str = Depends(require_scope("read")),
):
    settings = request.app.state.settings
    pseudonym = pseudonymize_user_id(user_id, settings)
    redis: Redis = request.app.state.redis
    try:
        already_heard = set(redis.zrevrange(f"user:{pseudonym}:tracks", 0, -1))
        popular = redis.zrevrange("tracks:popular", 0, settings.recommendation_limit + len(already_heard) - 1)
    except Exception as error:
        logger.error("Recommendation lookup failed: %s", error)
        raise HTTPException(status_code=503, detail="Recommendation service temporarily unavailable")
    selected = [track for track in popular if track not in already_heard][: settings.recommendation_limit]
    return RecommendationResponse(user_id=pseudonym[:12], track_ids=selected)


@app.get("/metrics", include_in_schema=False)
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
