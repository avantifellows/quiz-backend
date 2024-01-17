#!/bin/bash

# Define variables
echo "Defining variables..."
instanceName=$BASTION_HOST_INSTANCE_NAME
bastionHostPrivateKeyPath="/tmp/bastion_host_key.pem"
updateScript="update_target_group_ec2_codebase.sh"
envFile=".env"

# Save the private key to a file
echo "Decoding and saving the private key..."
echo "$BASTION_HOST_PRIVATE_KEY" | base64 --decode > $bastionHostPrivateKeyPath
chmod 600 $bastionHostPrivateKeyPath

# Check if the EC2 instance exists and is not terminated
echo "Checking if the EC2 instance with the name $instanceName exists and is not terminated..."
instanceId=$(aws ec2 describe-instances \
    --filters "Name=tag:Name,Values=$instanceName" "Name=instance-state-name,Values=pending,running,shutting-down,stopping,stopped" \
    --query "Reservations[*].Instances[*].InstanceId" \
    --region ap-south-1 --output text | head -n 1)

if [ -z "$instanceId" ]; then
    echo "Error: EC2 instance with the name $instanceName does not exist or is terminated."
    exit 1
fi

# Check instance state and start if necessary
echo "Checking the state of the instance..."
instanceState=$(aws ec2 describe-instance-status --instance-ids $instanceId --query "InstanceStatuses[*].InstanceState.Name" --region ap-south-1 --output text)

if [ "$instanceState" != "running" ]; then
    echo "Starting instance $instanceId..."
    AWS_PAGER="" aws ec2 start-instances --instance-ids $instanceId --region ap-south-1
    echo "Waiting for instance $instanceId to enter running state..."
    AWS_PAGER="" aws ec2 wait instance-running --instance-ids $instanceId --region ap-south-1
else
    echo "Instance $instanceId is already running."
fi

# Get public IP of the instance
echo "Retrieving public IP of the Bastion Host..."
bastionHostIP=$(aws ec2 describe-instances --instance-ids $instanceId --query "Reservations[*].Instances[*].PublicIpAddress" --region ap-south-1 --output text)

# Build the .env file from GitHub Secrets
echo "Building .env file..."
echo "MONGO_AUTH_CREDENTIALS=$MONGO_AUTH_CREDENTIALS" > $envFile
echo "BRANCH_NAME_TO_DEPLOY=$BRANCH_NAME_TO_DEPLOY" >> $envFile
echo "TARGET_GROUP_NAME=$TARGET_GROUP_NAME" >> $envFile

# Transfer the update script and .env file to the Bastion Host
echo "Transferring scripts to the Bastion Host at $bastionHostIP..."
scp -o StrictHostKeyChecking=no -i $bastionHostPrivateKeyPath deployment/$updateScript $envFile ec2-user@$bastionHostIP:/home/ec2-user/

# SSH into the Bastion Host and execute the update script
echo "Executing the update script on the Bastion Host..."
ssh -o StrictHostKeyChecking=no -i $bastionHostPrivateKeyPath ec2-user@$bastionHostIP "bash /home/ec2-user/$updateScript"

# Stop the instance
echo "Stopping instance $instanceId..."
AWS_PAGER="" aws ec2 stop-instances --instance-ids $instanceId --region ap-south-1

# Check if the instance is stopped
echo "Waiting for instance $instanceId to enter stopped state..."
AWS_PAGER="" aws ec2 wait instance-stopped --instance-ids $instanceId --region ap-south-1
echo "Instance $instanceId has been stopped."
