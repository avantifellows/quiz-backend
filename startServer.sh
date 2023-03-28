#!/bin/bash

# Default values for arguments
freshSync=false
source=""

# Parse command line arguments
# Two arguments are expected: --freshSync and --source
# --freshSync is a boolean argument, which when specified true, will start the server with a fresh sync from the source DB
# --source is a string argument, which tells the script which source DB to use, either staging or prod
while [[ $# -gt 0 ]]
do
  key="$1"

  case $key in
    -f|--freshSync)
    freshSync=true
    shift
    ;;
    -s|--source)
    source="$2"
    shift
    shift
    ;;
    *)
    echo "Invalid argument: $1"
    exit 1
    ;;
  esac
done

# start the mongod process
echo "Starting the mongod process"
brew services start mongodb-community@6.0

# Check the value of freshSync and start the sync process if true
if [ "$freshSync" = true ]; then
  echo -e "Fresh sync is true -- Going to remove current db and take a fresh sync \n \n"
  echo "Removing the existing data in the local database"
  mongosh --eval "db.getSiblingDB('quiz').dropDatabase()"
  echo "quiz DB dropped"
  echo -e "\n \n"
  # Check the value of source and sync from the appropriate DB
  case $source in
    "staging")
    echo -e "Taking a fresh sync from staging DB: \n \n"
    echo "Downlading the data from staging DB"
    mongodump --uri mongodb+srv://quiz:p%24%23p4h7y_Z44R-n@quiz-staging-m10.uocfg.mongodb.net/quiz
    echo "Data downloaded from staging DB, restoring the data in local DB"
    mongorestore --uri mongodb://127.0.0.1
    echo "Data restored in local DB!"
    ;;
    "prod")
    echo -e "Taking a fresh sync from Prod DB: \n \n"
    echo "Downlading the data from Prod DB"
    mongodump --uri mongodb+srv://quiz:p%24%23p4h7y_Z44R-n@quiz-prod-m10.uocfg.mongodb.net/quiz
    echo "Data downloaded from Prod DB, restoring the data in local DB"
    mongorestore --uri mongodb://127.0.0.1
    echo "Data restored in local DB!"
    ;;
    *)
    echo "Invalid value for source: $source. Allowed values are staging and prod"
    exit 1
    ;;
  esac

  echo -e "\n \n"
  echo "Removing the downloaded dump folder"
  rm -rf dump
fi

echo "Starting the server now"
source venv/bin/activate
cd app/
uvicorn main:app --reload
