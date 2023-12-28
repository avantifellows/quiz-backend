resource "aws_lb" "qb_lb" {
  name               = "qb-lb-asg"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.qb_sg_for_elb.id]
  subnets            = [aws_subnet.qb_subnet_1.id, aws_subnet.qb_subnet_1a.id]
  depends_on         = [aws_internet_gateway.qb_gw]
  tags = {
    Name = "qb-lb"
  }
}

resource "aws_lb_target_group" "qb_alb_tg" {
  name     = "qb-tf-lb-alb-tg"
  port     = 80
  protocol = "HTTP"
  vpc_id   = aws_vpc.qb_main.id
  health_check {
    path = "/docs"
  }
}

resource "aws_lb_listener" "qb_alb_listener" {
  load_balancer_arn = aws_lb.qb_lb.arn
  port              = "80"
  protocol          = "HTTP"

  default_action {
    target_group_arn = aws_lb_target_group.qb_alb_tg.arn
    type             = "forward"
  }
}

resource "aws_lb_listener" "qb_alb_https_listener" {
  load_balancer_arn = aws_lb.qb_lb.arn
  port              = "443"
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = "arn:aws:acm:ap-south-1:111766607077:certificate/9a8f45c3-e386-4ef7-bf4b-659180eb638f" # Replace with your certificate ARN

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.qb_alb_tg.arn
  }
}
