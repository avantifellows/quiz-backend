from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Custom settings which are used across the app.

    This model must NOT contain Mongo-related fields.
    Mongo configuration lives in MongoSettings below.

    Attributes
    ----------
    api_key_length : int
        the length of an organization's api key
    subset_size : int
        the number of questions which collectively can be called a `subset`.
        (read about subset pattern - https://www.notion.so/avantifellows/Database-4cfd0b2c9d6141fd88197649b0593318)
    """

    api_key_length: int = 20
    subset_size: int = 10


class MongoSettings(BaseSettings):
    """Mongo-specific settings, read from environment variables.

    Attributes
    ----------
    mongo_auth_credentials : str
        MongoDB connection URI (env: MONGO_AUTH_CREDENTIALS)
    mongo_db_name : str
        Database name (env: MONGO_DB_NAME, default: "quiz")
    mongo_max_pool_size : int
        Maximum connection pool size (env: MONGO_MAX_POOL_SIZE, default: 20)
    mongo_min_pool_size : int
        Minimum connection pool size (env: MONGO_MIN_POOL_SIZE, default: 5)
    """

    mongo_auth_credentials: str
    mongo_db_name: str = "quiz"
    mongo_max_pool_size: int = 20
    mongo_min_pool_size: int = 5


def get_mongo_settings():
    """Return a fresh MongoSettings instance from current environment.

    Must only be called inside functions, never at module scope.
    """
    return MongoSettings()
