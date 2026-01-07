# ECS Cluster
resource "aws_ecs_cluster" "quiz_backend" {
  name = "quiz-backend-${var.environment}"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = {
    Name = "quiz-backend-${var.environment}"
  }
}

# CloudWatch Log Group for ECS
resource "aws_cloudwatch_log_group" "quiz_backend" {
  name              = "/ecs/quiz-backend-${var.environment}"
  retention_in_days = 7 # Adjust for prod (30 or more)

  tags = {
    Name = "quiz-backend-${var.environment}"
  }
}

# ECS Task Definition
resource "aws_ecs_task_definition" "quiz_backend" {
  family                   = "quiz-backend-${var.environment}"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.task_cpu
  memory                   = var.task_memory
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  # Use ARM64 (Graviton) for ~20% cost savings
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "ARM64"
  }

  container_definitions = jsonencode([
    {
      name      = "quiz-backend"
      image     = "${aws_ecr_repository.quiz_backend.repository_url}:latest"
      essential = true

      portMappings = [
        {
          containerPort = var.app_port
          protocol      = "tcp"
        }
      ]

      environment = [
        {
          name  = "MONGO_AUTH_CREDENTIALS"
          value = var.mongo_auth_credentials
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.quiz_backend.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }

      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:${var.app_port}/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
    }
  ])

  tags = {
    Name = "quiz-backend-${var.environment}"
  }
}

# ECS Service
resource "aws_ecs_service" "quiz_backend" {
  name            = "quiz-backend-${var.environment}"
  cluster         = aws_ecs_cluster.quiz_backend.id
  task_definition = aws_ecs_task_definition.quiz_backend.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = data.aws_subnets.default.ids
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = true # Required for default VPC without NAT
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.quiz_backend.arn
    container_name   = "quiz-backend"
    container_port   = var.app_port
  }

  # Enable ECS Exec for debugging
  enable_execute_command = true

  # Ensure new task is healthy before stopping old one
  deployment_maximum_percent         = 200
  deployment_minimum_healthy_percent = 100

  # Wait for listener to be ready
  depends_on = [aws_lb_listener.http]

  tags = {
    Name = "quiz-backend-${var.environment}"
  }

  # Ignore changes to desired_count if manually scaled
  lifecycle {
    ignore_changes = [desired_count]
  }
}
