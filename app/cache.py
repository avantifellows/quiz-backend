import redis
import json

r = redis.Redis(decode_responses=True)

def cache_data(key: str, value, expire: int = 60):
    """ Cache data in Redis. """
    r.set(key, json.dumps(value), ex=expire)

def get_cached_data(key: str):
    """ Retrieve data from Redis cache. """
    cached_data = r.get(key)
    if cached_data:
        return json.loads(cached_data)
    return None

def invalidate_cache(key: str):
    """ Invalidate cache. """
    r.delete(key)