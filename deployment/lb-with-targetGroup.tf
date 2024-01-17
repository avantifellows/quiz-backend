resource "aws_lb" "lb" {
  name               = "${local.environment_prefix}lb-asg"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.sg_for_elb.id]
  subnets            = [aws_subnet.subnet_1.id, aws_subnet.subnet_1a.id]
  depends_on         = [aws_internet_gateway.gw]
  tags = {
    Name = "${local.environment_prefix}lb"
  }
}

resource "aws_lb_target_group" "alb_tg" {
  name     = "${local.environment_prefix}lb-alb-tg"
  port     = 80
  protocol = "HTTP"
  vpc_id   = aws_vpc.main.id
  health_check {
    path = "/docs"
  }
}

resource "aws_lb_listener" "alb_listener" {
  load_balancer_arn = aws_lb.lb.arn
  port              = "80"
  protocol          = "HTTP"

  default_action {
    target_group_arn = aws_lb_target_group.alb_tg.arn
    type             = "forward"
  }
}

resource "aws_lb_listener" "alb_https_listener" {
  load_balancer_arn = aws_lb.lb.arn
  port              = "443"
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = "arn:aws:acm:ap-south-1:111766607077:certificate/9a8f45c3-e386-4ef7-bf4b-659180eb638f" # Replace with your certificate ARN

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.alb_tg.arn
  }
}
