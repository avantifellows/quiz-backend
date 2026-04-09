#!/bin/bash

# Load environment variables from repo-root .env (if it exists).
# You can also export MONGO_AUTH_CREDENTIALS manually:
#   export MONGO_AUTH_CREDENTIALS="mongodb://127.0.0.1:27017"
if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

# Optional: start local MongoDB via systemd (skip if you manage Mongo separately)
echo "Starting the mongod process"
sudo systemctl start mongod

echo "Starting the server now"
source venv/bin/activate
cd app/
uvicorn main:app --reload
