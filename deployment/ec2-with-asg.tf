# IAM Role and Policy for EC2 Instances
resource "aws_iam_role" "ec2_role" {
  name_prefix = "${local.environment_prefix}ec2_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = "sts:AssumeRole",
        Effect = "Allow",
        Principal = {
          Service = "ec2.amazonaws.com"
        },
      },
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ec2_elb_access" {
  role       = aws_iam_role.ec2_role.name
  policy_arn = "arn:aws:iam::aws:policy/ElasticLoadBalancingReadOnly"
}

resource "aws_iam_role_policy_attachment" "ec2_describe_ec2" {
  role       = aws_iam_role.ec2_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ReadOnlyAccess"
}

resource "aws_iam_role_policy_attachment" "ec2_cloudwatch_logs" {
  role       = aws_iam_role.ec2_role.name
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
}

resource "aws_iam_instance_profile" "ec2_profile" {
  name_prefix = "${local.environment_prefix}ec2_profile"
  role        = aws_iam_role.ec2_role.name
}

# ASG with launch template
resource "aws_launch_template" "ec2_launch_templ" {
  name_prefix = "${local.environment_prefix}ec2_launch_templ"
  image_id    = "ami-0a0f1259dd1c90938"
  # instance_type = "t2.micro"
  instance_type = "c5a.large"
  user_data     = filebase64("user_data.sh")

  network_interfaces {
    associate_public_ip_address = false
    subnet_id                   = aws_subnet.subnet_2.id
    security_groups             = [aws_security_group.sg_for_ec2.id]
  }

  tag_specifications {
    resource_type = "instance"
    tags = {
      Name = "${local.environment_prefix}ec2"
    }
  }

  key_name = "AvantiFellows"

  iam_instance_profile {
    name = aws_iam_instance_profile.ec2_profile.name
  }
}

resource "aws_autoscaling_group" "asg" {
  name_prefix      = "${local.environment_prefix}asg"
  desired_capacity = 1
  max_size         = 1
  min_size         = 1

  # connect to the target group
  target_group_arns = [aws_lb_target_group.alb_tg.arn]

  vpc_zone_identifier = [aws_subnet.subnet_2.id]

  launch_template {
    id      = aws_launch_template.ec2_launch_templ.id
    version = "$Latest"
  }
}

resource "aws_instance" "redis_cache" {
  ami           = "ami-0ab84d9093b4c0d81" # Use an appropriate AMI for your region
  instance_type = "r6g.medium"              # Adjust the instance type as needed
  subnet_id     = aws_subnet.subnet_2.id  # Place the instance in a private subnet

  tags = {
    Name = "RedisCacheInstance"
  }

  key_name = "AvantiFellows"

  security_groups             = [aws_security_group.sg_for_redis.id]
  associate_public_ip_address = false
  iam_instance_profile = aws_iam_instance_profile.ec2_profile.name

  user_data = <<-EOF
                #!/bin/bash
                # sudo yum install -y redis
                # sudo systemctl start redis
                # sudo systemctl enable redis
                sudo dnf install -y redis6
                sudo systemctl start redis6
                sudo systemctl enable redis6
                sudo systemctl is-enabled redis6
                redis6-server --version
                redis6-cli ping
                # Update Redis configuration to listen on both localhost and the private IP
                PRIVATE_IP=$(aws ec2 describe-instances --filters "Name=tag:Name,Values=RedisCacheInstance" "Name=instance-state-name,Values=running" --query "Reservations[*].Instances[*].PrivateIpAddress" --region ap-south-1 --output text)
                echo $PRIVATE_IP > /tmp/private_ip.txt
                sudo sed -i "s/bind 127.0.0.1 -::1/bind 127.0.0.1 $PRIVATE_IP/" /etc/redis6/redis6.conf
                sudo systemctl restart redis6
                EOF
}

# Bastion Host Instance
resource "aws_instance" "bastion_host" {
  ami             = "ami-0a0f1259dd1c90938"
  instance_type   = "t2.micro"
  key_name        = "AvantiFellows"
  subnet_id       = aws_subnet.subnet_1.id # Place in a public subnet
  security_groups = [aws_security_group.sg_bastion.id]

  tags = {
    Name = "${local.environment_prefix}Bastion-Host"
  }

  iam_instance_profile = aws_iam_instance_profile.ec2_profile.name

  provisioner "file" {
    source      = "~/.ssh/AvantiFellows.pem"
    destination = "/home/ec2-user/AvantiFellows.pem"
  }

  provisioner "remote-exec" {
    inline = [
      "chmod 400 /home/ec2-user/AvantiFellows.pem"
    ]
  }

  connection {
    type        = "ssh"
    user        = "ec2-user"
    private_key = file("~/.ssh/AvantiFellows.pem")
    host        = self.public_ip
  }

  provisioner "local-exec" {
    command = "aws ec2 stop-instances --instance-ids ${self.id} --region ap-south-1"
    when    = create
  }
}
