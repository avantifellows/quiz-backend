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

# Install Git
echo "Installing Git..."
dnf install git -y

# Clone the repository
echo "Cloning the repository..."
git clone https://github.com/avantifellows/quiz-backend.git /home/ec2-user/quiz-backend

# Install Amazon CloudWatch Agent
# echo "Installing amazon-cloudwatch-agent..."
# sudo yum install amazon-cloudwatch-agent -y

# # start the agent
# echo "Starting amazon-cloudwatch-agent..."
# sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a fetch-config -m ec2 -c file:/home/ec2-user/quiz-backend/deployment/cloudwatch-agent-config.json -s

# # Install redis server
# sudo dnf install -y redis6
# sudo systemctl start redis6
# sudo systemctl enable redis6
# sudo systemctl is-enabled redis6
# redis6-server --version
# redis6-cli ping

# Navigate to the cloned directory
cd /home/ec2-user/quiz-backend

# Checkout the release branch
echo "Checking out the release branch..."
git checkout release

echo "Setting env file..."
touch .env

# Set up Python environment
echo "Setting up Python environment..."
python3 -m venv venv
source venv/bin/activate

# Install requirements
echo "Installing requirements..."
pip install -r app/requirements.txt

# Navigate to the app directory
cd app

# Start Uvicorn server
echo "Starting Uvicorn server..."
uvicorn main:app --host 0.0.0.0 --port 80 --workers 4
