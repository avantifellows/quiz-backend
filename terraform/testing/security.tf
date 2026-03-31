# Security group for ALB - allows HTTP from anywhere
resource "aws_security_group" "alb" {
  name        = "quiz-backend-${var.environment}-alb"
  description = "Security group for Quiz Backend ALB"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "HTTP from anywhere"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "quiz-backend-${var.environment}-alb"
  }
}

# Security group for ECS tasks - allows traffic from ALB only
resource "aws_security_group" "ecs_tasks" {
  name        = "quiz-backend-${var.environment}-ecs-tasks"
  description = "Security group for Quiz Backend ECS tasks"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description     = "HTTP from ALB"
    from_port       = var.app_port
    to_port         = var.app_port
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "quiz-backend-${var.environment}-ecs-tasks"
  }
}
