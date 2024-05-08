import redis
import json
import os

if "REDIS_HOST" not in os.environ:
    from dotenv import load_dotenv

    load_dotenv("../.env")

r_centralised = redis.Redis(
    host=os.getenv("REDIS_HOST") or "localhost", port=6379, decode_responses=True
)

r_local = redis.Redis(host="localhost", port=6379, decode_responses=True)


def cache_data(key: str, value, expire: int = 60 * 60 * 24):
    """Cache data in Redis."""
    r_centralised.set(key, json.dumps(value), ex=expire)


def cache_data_local(key: str, value, expire: int = 60 * 60 * 24):
    """Cache data in Redis."""
    r_local.set(key, json.dumps(value), ex=expire)


def get_cached_data(key: str):
    """Retrieve data from Redis cache."""
    cached_data = r_centralised.get(key)
    if cached_data:
        return json.loads(cached_data)
    return None


def get_cached_data_local(key: str):
    """Retrieve data from Redis cache."""
    cached_data = r_local.get(key)
    if cached_data:
        return json.loads(cached_data)
    return None


def get_keys(pattern: str):
    """Retrieve keys from Redis cache."""
    return r_centralised.keys(pattern)


def get_keys_local(pattern: str):
    """Retrieve keys from Redis cache."""
    return r_local.keys(pattern)


def invalidate_cache(key: str):
    """Invalidate cache."""
    r_centralised.delete(key)


def invalidate_cache_local(key: str):
    """Invalidate cache."""
    r_local.delete(key)
