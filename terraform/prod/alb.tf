# Application Load Balancer
resource "aws_lb" "quiz_backend" {
  name               = "quiz-backend-${var.environment}"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = data.aws_subnets.default.ids

  enable_deletion_protection = true

  tags = {
    Name = "quiz-backend-${var.environment}"
  }
}

# Target Group - ECS tasks will register here
resource "aws_lb_target_group" "quiz_backend" {
  name        = "quiz-backend-${var.environment}"
  port        = var.app_port
  protocol    = "HTTP"
  vpc_id      = data.aws_vpc.default.id
  target_type = "ip" # Required for Fargate

  health_check {
    enabled             = true
    healthy_threshold   = 2
    interval            = 30
    matcher             = "200"
    path                = "/health"
    port                = "traffic-port"
    protocol            = "HTTP"
    timeout             = 5
    unhealthy_threshold = 3
  }

  tags = {
    Name = "quiz-backend-${var.environment}"
  }
}

# HTTP Listener
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.quiz_backend.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.quiz_backend.arn
  }
}
