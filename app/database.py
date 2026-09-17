from pymongo import AsyncMongoClient
from settings import get_mongo_settings

_client = None


def get_configured_db_name():
    return get_mongo_settings().mongo_db_name


def init_db():
    global _client
    if _client is None:
        mongo_settings = get_mongo_settings()
        _client = AsyncMongoClient(
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


def get_quiz_db():
    if _client is None:
        raise RuntimeError("Database client is not initialized")
    return _client[get_configured_db_name()]


async def close_db():
    global _client
    if _client is not None:
        await _client.close()
        _client = None
