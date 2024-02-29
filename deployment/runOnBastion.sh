#!/bin/bash

# extract TARGET_GROUP_NAME from .env file and store it in an environment variable
TARGET_GROUP_NAME=$(grep TARGET_GROUP_NAME .env | cut -d '=' -f2)

# extract REDIS_HOST from .env file and store it in an environment variable
REDIS_HOST=$(grep REDIS_HOST .env | cut -d '=' -f2)

# Define variables
echo "[EC2 Action] Defining variables..."
targetGroupName=$TARGET_GROUP_NAME
region="ap-south-1" # replace with your actual region
account_id="111766607077" # replace with your actual account ID

# Fetch the ARN of the target group by its name
echo "[EC2 Action] Fetching ARN for target group named $targetGroupName..."
targetGroupArn=$(aws elbv2 describe-target-groups --names $targetGroupName --query "TargetGroups[0].TargetGroupArn" --output text --region $region)

# Check if we successfully retrieved the ARN
if [ -z "$targetGroupArn" ]; then
    echo "[EC2 Action] Error: Could not retrieve ARN for target group named $targetGroupName."
    exit 1
fi

echo "[EC2 Action] Found ARN for target group: $targetGroupArn"

keyPath="/home/ec2-user/AvantiFellows.pem"
envFile="/home/ec2-user/.env"
pathToCloudwatchConfig="/home/ec2-user/quiz-backend/deployment/cloudwatch-agent-config.json"

# Fetch the instance IDs of the target group using the ARN
echo "[EC2 Action] Fetching instance IDs of the target group..."
instanceIds=$(aws elbv2 describe-target-health --target-group-arn $targetGroupArn --query "TargetHealthDescriptions[*].Target.Id" --output text --region $region)

echo "[EC2 Action] Fetching private IP addresses of the instances..."
privateIps=$(aws ec2 describe-instances --instance-ids $instanceIds --query "Reservations[*].Instances[*].PrivateIpAddress" --output text --region $region)

# Convert the space-separated strings into arrays
instanceIdsArray=($instanceIds)
privateIpsArray=($privateIps)

# extract BRANCH_NAME_TO_DEPLOY from .env file and store it in an environment variable
BRANCH_NAME_TO_DEPLOY=$(grep BRANCH_NAME_TO_DEPLOY $envFile | cut -d '=' -f2)

for i in "${!instanceIdsArray[@]}"; do
    id=${instanceIdsArray[$i]}
    private_ip=${privateIpsArray[$i]}
    echo "[EC2 Action] Processing instance ID: $id"

    # Get private IP of the instance
    echo "[EC2 Action] Getting private IP of instance $id..."
    instanceIp=$(aws ec2 describe-instances --instance-ids $id --query "Reservations[*].Instances[*].PrivateIpAddress" --output text)

    echo "[EC2 Action] Changing access permissions for the directory..."
    ssh -o StrictHostKeyChecking=no -i $keyPath ec2-user@$instanceIp "sudo chown -R ec2-user:ec2-user /home/ec2-user/quiz-backend"

    # Transfer .env file
    echo "[EC2 Action] Transferring .env file to instance $id at IP $instanceIp..."
    scp -o StrictHostKeyChecking=no -i $keyPath $envFile ec2-user@$instanceIp:/home/ec2-user/quiz-backend

    # Execute commands on the instance
    echo "[EC2 Action] Executing commands on instance $id..."
    RANDOM_MINUTE=$((9 + RANDOM % 15))
    ssh -o StrictHostKeyChecking=no -i $keyPath ec2-user@$instanceIp << EOF
        echo "[EC2 Action] Stopping any process running on port 80..."
        sudo fuser -k 80/tcp
        sudo su

        echo "[EC2 Action] Updating codebase and restarting the application..."
        cd /home/ec2-user/quiz-backend
        echo "Changed directory to /home/ec2-user/quiz-backend"
        git checkout $BRANCH_NAME_TO_DEPLOY
        echo "Checked out branch $BRANCH_NAME_TO_DEPLOY"
        git pull origin $BRANCH_NAME_TO_DEPLOY
        echo "Pulled latest changes from $BRANCH_NAME_TO_DEPLOY"
        echo $id
        echo "HOST_IP=$instanceIp" >> .env
        echo "Added host ip to .env file"

        echo "trying to activate venv"
        source venv/bin/activate
        echo "activated venv"
        pip install -r app/requirements.txt
        echo "installed requirements"
        cd app
        echo "changed directory to app"

        # if the log shipper script exists, make it executable and setup cron for it
        if [ -f "log_shipper.sh" ]; then
            echo "Making log_shipper.sh executable..."
            chmod +x log_shipper.sh
            echo "Setting up cron for log_shipper.sh..."
            (crontab -l 2>/dev/null | grep -v 'log_shipper.sh' ; echo "*/$RANDOM_MINUTE * * * * /home/ec2-user/quiz-backend/app/log_shipper.sh 2>> /home/ec2-user/quiz-backend/app/log_shipper_error.log") | crontab -
        fi

        # Setup cron for redis write back script
        echo "Setting up cron for redis write back script..."
        cd /home/ec2-user/quiz-backend/app/cache
        if [ -f "cache_write_back.sh" ]; then
            echo "Making cache_write_back.sh executable..."
            chmod +x cache_write_back.sh
            # run every night at 9:30 PM UTC which is 3:00 AM IST
            (crontab -l 2>/dev/null | grep -v 'cache_write_back.sh' ; echo "30 21 * * * /home/ec2-user/quiz-backend/app/cache/cache_write_back.sh 2>> /home/ec2-user/quiz-backend/logs/cache_write_back_cron.log") | crontab -
        fi

        nohup uvicorn main:app --host 0.0.0.0 --port 80 --workers 8 > /home/ec2-user/quiz-backend/logs/uvicorn.log 2>&1 &
        disown
EOF
    echo "[EC2 Action] Completed actions on instance $id."
done

# Transfer .env file to the redis instance
echo "[EC2 Action] Transferring .env file to Redis instance..."

# Change access permissions for the directory
echo "[EC2 Action] Changing access permissions for the directory in redis instance..."
ssh -o StrictHostKeyChecking=no -i $keyPath ec2-user@$REDIS_HOST "sudo chown -R ec2-user:ec2-user /home/ec2-user/quiz-backend"

# Transfer .env file
echo "[EC2 Action] Transferring .env file to Redis instance..."
scp -o StrictHostKeyChecking=no -i $keyPath $envFile ec2-user@$REDIS_HOST:/home/ec2-user/quiz-backend

# Execute commands on the Redis instance
echo "[EC2 Action] Executing commands on Redis instance..."
ssh -o StrictHostKeyChecking=no -i $keyPath ec2-user@$REDIS_HOST << EOF
    echo "[EC2 Action] Updating codebase and restarting the application..."
    cd /home/ec2-user/quiz-backend
    git checkout $BRANCH_NAME_TO_DEPLOY
    git pull origin $BRANCH_NAME_TO_DEPLOY

    source venv/bin/activate
    pip install -r app/requirements.txt
    cd app
EOF
echo "[EC2 Action] Completed actions on Redis instance."


echo "[EC2 Action] Completed updating all instances in target group."
