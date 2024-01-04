#!/bin/bash

# Define variables
instanceName="qb-Bastion-Host"
bastionHostPrivateKeyPath="/tmp/bastion_host_key.pem"
updateScript="update_target_group_ec2_codebase.sh"
envFile=".env"

# Save the private key to a file
# echo "$BASTION_HOST_PRIVATE_KEY" > $bastionHostPrivateKeyPath
echo "$BASTION_HOST_PRIVATE_KEY" | base64 --decode > $bastionHostPrivateKeyPath
chmod 600 $bastionHostPrivateKeyPath

# Check if the EC2 instance exists
instanceId=$(aws ec2 describe-instances --query "Reservations[*].Instances[*].{ID:InstanceId,Name:Tags[?Key=='Name']|[0].Value}" --region ap-south-1 --output text | grep "$instanceName" | awk '{print $1}')

if [ -z "$instanceId" ]; then
    echo "Error: EC2 instance with the name $instanceName does not exist."
    exit 1
fi

# Check instance state and start if necessary
instanceState=$(aws ec2 describe-instance-status --instance-ids $instanceId --query "InstanceStatuses[*].InstanceState.Name" --region ap-south-1 --output text)

if [ "$instanceState" != "running" ]; then
    echo "Starting instance $instanceId..."
    AWS_PAGER="" aws ec2 start-instances --instance-ids $instanceId --region ap-south-1
    echo "Waiting for instance to enter running state..."
    AWS_PAGER="" aws ec2 wait instance-running --instance-ids $instanceId --region ap-south-1
fi

# Get public IP of the instance
bastionHostIP=$(aws ec2 describe-instances --instance-ids $instanceId --query "Reservations[*].Instances[*].PublicIpAddress" --region ap-south-1 --output text)

# Build the .env file from GitHub Secrets
echo "MONGO_AUTH_CREDENTIALS=$MONGO_AUTH_CREDENTIALS" > $envFile

# Transfer the update script and .env file to the Bastion Host
scp -o StrictHostKeyChecking=no -i $bastionHostPrivateKeyPath deployment/$updateScript $envFile ec2-user@$bastionHostIP:/home/ec2-user/

# SSH into the Bastion Host and execute the update script
ssh -o StrictHostKeyChecking=no -i $bastionHostPrivateKeyPath ec2-user@$bastionHostIP "bash /home/ec2-user/$updateScript"

# stop the instance
echo "Stopping instance $instanceId..."
AWS_PAGER="" aws ec2 stop-instances --instance-ids $instanceId --region ap-south-1

# check if the instance is stopped
echo "Waiting for instance to enter stopped state..."
AWS_PAGER="" aws ec2 wait instance-stopped --instance-ids $instanceId --region ap-south-1