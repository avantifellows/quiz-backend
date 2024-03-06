#!/bin/bash

# This script is repeatedly called by the cron job to ship logs to S3.
# The fastapi app generates logs in the LOG_DIR directory, and this script
# uploads them to the LOGS_S3_BUCKET S3 bucket after checking for any name collisions.

# Set the directory where your logs are stored
LOG_DIR="/home/ec2-user/quiz-backend/logs"

# Load the env variables
source "/home/ec2-user/quiz-backend/.env"

# Change to the log directory
cd "$LOG_DIR"

# List all rotated log files with a timestamp. This format has been specified in the log configuration.
for log_file in app_*_*_????_??_??_??_??_??.log; do
    if [[ -f "$log_file" ]]; then
        # Check if the file exists in the S3 bucket
        if aws s3 ls "s3://$LOGS_S3_BUCKET/$log_file" >/dev/null 2>&1; then
            # File exists, append a number to the filename
            base_name="${log_file%.*}"
            extension="${log_file##*.}"
            counter=1
            while aws s3 ls "s3://$LOGS_S3_BUCKET/${base_name}_$counter.$extension" >/dev/null 2>&1; do
                ((counter++))
            done
            new_name="${base_name}_$counter.$extension"
            aws s3 cp "$log_file" "s3://$LOGS_S3_BUCKET/$new_name"
        else
            # File does not exist, upload with the original name
            aws s3 cp "$log_file" "s3://$LOGS_S3_BUCKET/$log_file"
        fi
        # Delete the local log file
        rm "$log_file"
    fi
done


# if uvicorn log file exists in the folder, rename this file by attaching a timestamp to it and upload it to S3
# and create a new one with the same name
uvicorn_log_file="/home/ec2-user/quiz-backend/logs/uvicorn.log"
if [[ -f "$uvicorn_log_file" ]]; then
    timestamp=$(date "+%Y_%m_%d_%H_%M_%S")
    aws s3 cp "$uvicorn_log_file" "s3://$LOGS_S3_BUCKET/uvicorn_$timestamp.log"
    > "$uvicorn_log_file"
fi
