import os
from pymongo import MongoClient

# this is required for loading environment variables when
# running the app locally as the environment variable should
# be set when the app is running on staging/production by Github Actions
print(os.environ)
if "MONGO_AUTH_CREDENTIALS" not in os.environ:
    from dotenv import load_dotenv

    print("entered here")
    load_dotenv("../.env")

client = MongoClient(os.getenv("MONGO_AUTH_CREDENTIALS"))
