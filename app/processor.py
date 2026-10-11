from redis import Redis

from app.config import Settings
from app.models import EventType, MusicEvent
from app.storage import archive_event


PROCESS_USER_EVENT = """
if redis.call('SET', KEYS[1], '1', 'NX', 'EX', ARGV[1]) == false then
    return 0
end
redis.call('ZINCRBY', KEYS[2], ARGV[2], ARGV[3])
redis.call('EXPIRE', KEYS[2], ARGV[1])
redis.call('ZREMRANGEBYRANK', KEYS[2], 0, -1001)
return 1
"""

PROCESS_GLOBAL_EVENT = """
if redis.call('SET', KEYS[1], '1', 'NX', 'EX', ARGV[1]) == false then
    return 0
end
redis.call('ZINCRBY', KEYS[2], ARGV[2], ARGV[3])
redis.call('EXPIRE', KEYS[2], ARGV[1])
redis.call('ZREMRANGEBYRANK', KEYS[2], 0, -100001)
return 1
"""

DEDUPLICATION_TTL_SECONDS = 691200


def process_event(event: MusicEvent, redis: Redis, settings: Settings) -> bool:
    archive_event(event, settings)
    score = 2 if event.event_type == EventType.like else (1 if event.event_type == EventType.play else 0)
    user_result = redis.eval(
        PROCESS_USER_EVENT,
        2,
        f"user:{{{event.user_id}}}:seen:{event.event_id}",
        f"user:{{{event.user_id}}}:tracks",
        DEDUPLICATION_TTL_SECONDS,
        score,
        event.track_id,
    )
    global_result = redis.eval(
        PROCESS_GLOBAL_EVENT,
        2,
        f"{{global}}:seen:{event.event_id}",
        "{global}:tracks:popular",
        DEDUPLICATION_TTL_SECONDS,
        score,
        event.track_id,
    )
    return bool(user_result or global_result)
