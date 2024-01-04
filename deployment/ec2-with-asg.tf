# ASG with launch template
resource "aws_launch_template" "qb_ec2_launch_templ" {
  name_prefix   = "qb-ec2-launch-template"
  image_id      = "ami-0a0f1259dd1c90938"
  instance_type = "t2.micro"
  user_data     = filebase64("user_data.sh")

  network_interfaces {
    associate_public_ip_address = false
    subnet_id                   = aws_subnet.qb_subnet_2.id
    security_groups             = [aws_security_group.qb_sg_for_ec2.id]
  }

  tag_specifications {
    resource_type = "instance"
    tags = {
      Name = "qb-ec2"
    }
  }

  key_name = "AvantiFellows" # Add this line to assign a key pair
}

resource "aws_autoscaling_group" "qb_asg" {
  desired_capacity = 1
  max_size         = 2
  min_size         = 1

  # connect to the target group
  target_group_arns = [aws_lb_target_group.qb_alb_tg.arn]

  vpc_zone_identifier = [aws_subnet.qb_subnet_2.id]

  launch_template {
    id      = aws_launch_template.qb_ec2_launch_templ.id
    version = "$Latest"
  }
}

# Bastion Host Instance
resource "aws_instance" "qb_bastion_host" {
  ami             = "ami-0a0f1259dd1c90938" # Use an appropriate AMI
  instance_type   = "t2.micro"
  key_name        = "AvantiFellows"
  subnet_id       = aws_subnet.qb_subnet_1.id # Place in a public subnet
  security_groups = [aws_security_group.qb_sg_bastion.id]

  tags = {
    Name = "qb-Bastion-Host"
  }

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
