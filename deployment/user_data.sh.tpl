#!/bin/bash

# Specify the log file
LOG_FILE="/var/log/user_data.log"

# Use exec to redirect all stdout and stderr to the log file from this point on
exec > >(tee -a ${LOG_FILE}) 2>&1

echo "Starting user_data script execution"

# No need for 'sudo su' when running as user data, the script runs with root privileges by default

# Update the system
echo "Running system update..."
yum update -y

# # Install redis server
sudo dnf install -y redis6
sudo systemctl start redis6
sudo systemctl enable redis6
sudo systemctl is-enabled redis6
redis6-server --version
redis6-cli ping

# Install cronie
sudo yum install -y cronie
sudo systemctl start crond.service
sudo systemctl enable crond.service

# Install Git
echo "Installing Git..."
dnf install git -y

# Clone the repository
echo "Cloning the repository..."
git clone https://github.com/avantifellows/quiz-backend.git /home/ec2-user/quiz-backend

# echo "Changing access permissions for the directory..."
# sudo chown -R ec2-user:ec2-user /home/ec2-user/quiz-backend

echo "Checking out a branch..."
cd /home/ec2-user/quiz-backend
git stash
git checkout ${BRANCH_NAME_TO_DEPLOY}
git pull origin ${BRANCH_NAME_TO_DEPLOY}

echo "Setting env file..."
touch .env
echo "MONGO_AUTH_CREDENTIALS=${MONGO_AUTH_CREDENTIALS}" >> .env
echo "BRANCH_NAME_TO_DEPLOY=${BRANCH_NAME_TO_DEPLOY}" >> .env
echo "TARGET_GROUP_NAME=${TARGET_GROUP_NAME}" >> .env
REDIS_HOST=$(aws ec2 describe-instances --filters "Name=tag:Name,Values=${environment_prefix}RedisCacheInstance" "Name=instance-state-name,Values=running" --query "Reservations[*].Instances[*].PrivateIpAddress" --region ap-south-1 --output text)
echo "REDIS_HOST=$REDIS_HOST" >> .env
echo "ENVIRONMENT_PREFIX=${environment_prefix}" >> .env
echo "LOGS_S3_BUCKET=${LOGS_S3_BUCKET}" >> .env
HOST_IP=$(curl http://169.254.169.254/latest/meta-data/local-ipv4)
echo "HOST_IP=$HOST_IP" >> .env

# Set up Python environment
echo "Setting up Python environment..."
python3 -m venv venv
source venv/bin/activate

# Install requirements
echo "Installing requirements..."
pip install -r app/requirements.txt

# Navigate to the app directory
cd app

# if the log shipper script exists, make it executable and setup cron for it
if [ -f "log_shipper.sh" ]; then
    echo "Making log_shipper.sh executable..."
    chmod +x log_shipper.sh
    echo "Setting up cron for log_shipper.sh..."
    RANDOM_MINUTE=$((9 + RANDOM % 15))
    (crontab -l 2>/dev/null | grep -v 'log_shipper.sh' ; echo "*/$RANDOM_MINUTE * * * * /home/ec2-user/quiz-backend/app/log_shipper.sh 2>> /home/ec2-user/quiz-backend/app/log_shipper_error.log") | crontab -
fi

# Start Uvicorn server
echo "Starting Uvicorn server..."
uvicorn main:app --host 0.0.0.0 --port 80 --workers 8 > /home/ec2-user/quiz-backend/app/uvicorn.log 2>&1 &


# Install Amazon CloudWatch Agent
# echo "Installing amazon-cloudwatch-agent..."
# sudo yum install amazon-cloudwatch-agent -y

# # start the agent
# echo "Starting amazon-cloudwatch-agent..."
# sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a fetch-config -m ec2 -c file:/home/ec2-user/quiz-backend/deployment/cloudwatch-agent-config.json -s
