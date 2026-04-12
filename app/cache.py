import json
import time
import redis.asyncio as redis
from fastapi.encoders import jsonable_encoder
from logger_config import get_logger
from settings import get_cache_settings
from database import get_quiz_db
from services.quiz_fixups import apply_quiz_backwards_compatibility_fixup

logger = get_logger()

redis_client = None
_last_error_log_ts = 0.0
_last_connect_attempt_ts = 0.0

# Per-family hit/miss/error counters for periodic summary logging
_stats = {}
_last_stats_log_ts = 0.0
_STATS_LOG_INTERVAL = 60.0


def _cache_settings():
    return get_cache_settings()


def _bump_stat(family: str, field: str):
    """Increment an in-memory counter for cache telemetry."""
    if family not in _stats:
        _stats[family] = {"hits": 0, "misses": 0, "errors": 0}
    _stats[family][field] += 1


def _maybe_log_stats():
    """Log and reset accumulated cache stats if the interval has elapsed."""
    global _last_stats_log_ts
    now = time.time()
    if now - _last_stats_log_ts < _STATS_LOG_INTERVAL:
        return
    _last_stats_log_ts = now
    for family, counts in _stats.items():
        if counts["hits"] or counts["misses"] or counts["errors"]:
            logger.info(
                f"event=cache_stats family={family} "
                f"hits={counts['hits']} misses={counts['misses']} errors={counts['errors']}"
            )
    _stats.clear()


async def init_cache():
    """Best-effort Redis connection at startup. Never raises."""
    await _ensure_cache_client(force=True)


async def _close_old_client(old_client):
    """Close an old Redis client, suppressing errors to avoid masking the caller's context."""
    if old_client is not None:
        try:
            await old_client.aclose()
        except Exception:
            pass


async def _ensure_cache_client(force: bool = False):
    global redis_client, _last_connect_attempt_ts
    settings = _cache_settings()
    if not settings.cache_enabled:
        old_client = redis_client
        redis_client = None
        await _close_old_client(old_client)
        return None
    if redis_client is not None and not force:
        return redis_client

    now = time.time()
    if not force and now - _last_connect_attempt_ts < 5:
        return None
    _last_connect_attempt_ts = now

    old_client = redis_client
    try:
        candidate = redis.Redis.from_url(
            settings.redis_url,
            max_connections=settings.redis_max_connections,
            decode_responses=True,
        )
        await candidate.ping()
        redis_client = candidate
        await _close_old_client(old_client)
        return redis_client
    except Exception as e:
        redis_client = None
        await _close_old_client(old_client)
        if _should_log_cache_error():
            logger.warning(
                f"event=cache op=connect result=error family=system "
                f"detail=redis_unavailable error={type(e).__name__}"
            )
        return None


async def close_cache():
    """Shutdown hook — close the Redis client if open."""
    global redis_client
    if redis_client is not None:
        try:
            await redis_client.aclose()
        except Exception:
            pass
        redis_client = None


def _should_log_cache_error() -> bool:
    global _last_error_log_ts
    now = time.time()
    if now - _last_error_log_ts > 60:
        _last_error_log_ts = now
        return True
    return False


def cache_key(family: str, *parts: str) -> str:
    """Build a namespaced cache key, e.g. cache:v1:quiz:abc123."""
    settings = _cache_settings()
    return f"cache:{settings.cache_namespace}:{family}:{':'.join(parts)}"


def cache_family(key: str) -> str:
    """Extract the family segment from a full cache key for log grouping.
    e.g. 'cache:v1:quiz:abc123' -> 'quiz'."""
    parts = key.split(":")
    return parts[2] if len(parts) > 2 else "unknown"


async def cache_get(key: str):
    """Return cached JSON data, or None on miss / disabled cache / Redis failure."""
    family = cache_family(key)
    client = await _ensure_cache_client()
    if client is None:
        _bump_stat(family, "misses")
        _maybe_log_stats()
        return None
    try:
        data = await client.get(key)
        if data is not None:
            _bump_stat(family, "hits")
            _maybe_log_stats()
            return json.loads(data)
        _bump_stat(family, "misses")
        _maybe_log_stats()
    except Exception as e:
        global redis_client
        old_client = redis_client
        redis_client = None
        await _close_old_client(old_client)
        _bump_stat(family, "errors")
        _maybe_log_stats()
        if _should_log_cache_error():
            logger.warning(
                f"event=cache op=get result=error family={family} "
                f"key_ref={key} error={type(e).__name__}"
            )
    return None


async def cache_set(key: str, value, ttl_seconds: int = 3600):
    """Write JSON-safe canonical data into Redis. Never raises to request handlers."""
    family = cache_family(key)
    client = await _ensure_cache_client()
    if client is None:
        return
    try:
        payload = json.dumps(jsonable_encoder(value))
        await client.setex(key, ttl_seconds, payload)
    except Exception as e:
        global redis_client
        old_client = redis_client
        redis_client = None
        await _close_old_client(old_client)
        _bump_stat(family, "errors")
        _maybe_log_stats()
        if _should_log_cache_error():
            logger.warning(
                f"event=cache op=set result=error family={family} "
                f"key_ref={key} error={type(e).__name__}"
            )


async def get_cached_quiz(quiz_id: str) -> dict | None:
    """Shared cached quiz loader. Returns the canonical quiz document or None if not found.

    On cache miss: reads from MongoDB, runs backwards-compatibility fixup if needed,
    caches the result with 1h TTL. Routes handle their own 404 responses.
    If the fixup DB write-back fails, the HTTPException propagates (500) and the
    quiz is not cached.
    """
    cached = await cache_get(cache_key("quiz", quiz_id))
    if cached is not None:
        return cached

    db = get_quiz_db()
    quiz = await db.quizzes.find_one({"_id": quiz_id})
    if quiz is None:
        return None

    await apply_quiz_backwards_compatibility_fixup(quiz_id, quiz)
    await cache_set(cache_key("quiz", quiz_id), quiz, ttl_seconds=3600)
    return quiz
