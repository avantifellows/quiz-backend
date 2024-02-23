resource "aws_security_group" "sg_for_elb" {
  name        = "${local.environment_prefix}sg-for-elb"
  description = "security group for ELB"
  vpc_id      = aws_vpc.main.id

  ingress {
    description      = "Allow HTTP from anywhere"
    from_port        = 80
    to_port          = 80
    protocol         = "tcp"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  ingress {
    description      = "Allow HTTPS from anywhere"
    from_port        = 443
    to_port          = 443
    protocol         = "tcp"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  egress {
    description = "Allow all traffic to anywhere"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "sg_for_ec2" {
  name        = "${local.environment_prefix}sg-for-ec2"
  description = "security group for EC2"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Allow http from load balancer"
    from_port       = 80
    to_port         = 80
    protocol        = "tcp"
    security_groups = [aws_security_group.sg_for_elb.id]
  }

  # Allow Redis traffic from the Redis instance
  ingress {
    description     = "Allow Redis traffic from Redis instance"
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.sg_for_redis.id]
  }

  egress {
    description = "Allow all traffic to anywhere"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "sg_for_redis" {
  name        = "${local.environment_prefix}sg-for-redis"
  description = "Security group for Redis"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "Allow all inbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "Allow all traffic to anywhere"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}


# Security Group for Bastion Host
resource "aws_security_group" "sg_bastion" {
  name        = "${local.environment_prefix}sg-bastion"
  description = "Bastion host security group"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "SSH from anywhere"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group_rule" "allow_ssh_from_bastion_to_ec2" {
  type              = "ingress"
  from_port         = 22
  to_port           = 22
  protocol          = "tcp"
  cidr_blocks       = ["${aws_instance.bastion_host.private_ip}/32"] # Use the private IP of the bastion host
  security_group_id = aws_security_group.sg_for_ec2.id
}

resource "aws_security_group_rule" "allow_ssh_from_bastion_to_redis" {
  type              = "ingress"
  from_port         = 22
  to_port           = 22
  protocol          = "tcp"
  cidr_blocks       = ["${aws_instance.bastion_host.private_ip}/32"] # Use the private IP of the bastion host
  security_group_id = aws_security_group.sg_for_redis.id
}
