#!/bin/bash
# Set the directory where your logs are stored
# LOG_DIR="/Users/deepanshmathur/Documents/AF/quiz-backend/logs"
LOG_DIR="/home/ec2-user/quiz-backend/logs"

source "/home/ec2-user/quiz-backend/.env"

# Change to the log directory
cd "$LOG_DIR"

# List all rotated log files with a timestamp (modify the pattern as needed)
for log_file in app.????_??_??_??_??_??.log; do
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
