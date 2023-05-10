#!/bin/bash

# Default values for arguments
freshSync=false
source=""

# Parse command line arguments
# Two arguments are expected: --freshSync and --source
# --freshSync is a boolean argument, which when specified true, will start the server with a fresh sync from the source DB
# --source is a string argument, the mongo DB uri, which tells the script which cloud DB to use for the sync
while [[ $# -gt 0 ]]
do
  key="$1"

  case $key in
    -f|--freshSync)
    freshSync=true
    shift
    ;;
    -s|--source)
    if [[ -z "$2" ]] || [[ "$2" =~ ^-.* ]]; then
      echo "Error: --source requires a non-empty argument"
      exit 1
    fi
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

# Check if freshSync is true and source is empty
if $freshSync && [[ -z $source ]]; then
  echo "Error: --freshSync requires --source to be specified"
  exit 1
fi

# Check if source is specified and freshSync is false
if [[ -n $source ]] && ! $freshSync; then
  echo "Error: --source requires --freshSync to be specified"
  exit 1
fi

# start the mongod process
echo "Starting the mongod process"
sudo systemctl start mongod

# Check the value of freshSync and start the sync process if true
if [ "$freshSync" = true ]; then
  echo -e "Fresh sync is true -- Going to remove current db and take a fresh sync \n \n"
  echo "Removing the existing data in the local database"
  mongosh --eval "db.getSiblingDB('quiz').dropDatabase()"
  echo "quiz DB dropped"
  echo -e "\n \n"

  echo -e "Taking a fresh sync from the specified DB: \n \n"
  echo "Downlading the data from DB"
  mongodump --uri $source
  if [ $? -eq 1 ]; then
    echo "Error while downloading the data from the cloud DB. Please check your mongo DB URI and try again"
    exit 1
  fi
  echo "Data downloaded from cloud DB, restoring the data in local DB"
  mongorestore --uri mongodb://127.0.0.1
  echo "Data restored in local DB!"

  echo -e "\n \n"
  echo "Removing the downloaded dump folder"
  rm -rf dump
fi

echo "Starting the server now"
source venv/bin/activate
cd app/
uvicorn main:app --reload
