import os
from pymongo import MongoClient

# this is required for loading environment variables when
# running the app locally as the environment variable should
# be set when the app is running on staging/production by Github Actions
if "MONGO_AUTH_CREDENTIALS" not in os.environ:
    from dotenv import load_dotenv

    load_dotenv("../.env")

# Connection pool configuration for ECS
# These settings ensure efficient connection reuse while remaining
# compatible with Lambda (which will just use fewer connections)
client = MongoClient(
    os.getenv("MONGO_AUTH_CREDENTIALS"),
    # Connection Pool Settings
    maxPoolSize=20,  # Max connections this container will use
    minPoolSize=5,  # Keep 5 connections always open
    # Timeout Settings
    maxIdleTimeMS=30000,  # Close idle connections after 30 seconds
    connectTimeoutMS=5000,  # Fail fast if can't connect in 5 seconds
    serverSelectionTimeoutMS=5000,
    # Reliability Settings
    retryWrites=True,  # Retry failed writes automatically
    retryReads=True,  # Retry failed reads automatically
)
