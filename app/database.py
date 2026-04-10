from pymongo import MongoClient
from settings import get_mongo_settings

_client = None
client = None  # Backwards compat for routers; use get_quiz_db() in new code.


def get_configured_db_name():
    return get_mongo_settings().mongo_db_name


def init_db():
    global _client, client
    if _client is None:
        mongo_settings = get_mongo_settings()
        _client = MongoClient(
            mongo_settings.mongo_auth_credentials,
            # Connection Pool Settings
            maxPoolSize=mongo_settings.mongo_max_pool_size,
            minPoolSize=mongo_settings.mongo_min_pool_size,
            # Timeout Settings
            maxIdleTimeMS=30000,
            connectTimeoutMS=5000,
            serverSelectionTimeoutMS=5000,
            # Reliability Settings
            retryWrites=True,
            retryReads=True,
        )
        client = _client


def get_quiz_db():
    if _client is None:
        raise RuntimeError("Database client is not initialized")
    return _client[get_configured_db_name()]


def close_db():
    global _client, client
    if _client is not None:
        _client.close()
        _client = None
        client = None
