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
uvicorn main:app --host 0.0.0.0 --port 80
