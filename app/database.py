import os
from pymongo import MongoClient

# Load .env for local development — in CI/ECS the env var is set directly.
# load_dotenv() searches upward from CWD, so it works from both the repo root
# and the app/ directory.
if "MONGO_AUTH_CREDENTIALS" not in os.environ:
    from dotenv import load_dotenv

    load_dotenv()

if not os.getenv("MONGO_AUTH_CREDENTIALS"):
    raise RuntimeError(
        "MONGO_AUTH_CREDENTIALS is not set. "
        "Set it in your environment or in a .env file at the repo root."
    )

# Connection pool configuration for ECS Fargate
# Each container maintains a pool of reusable connections to MongoDB
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
