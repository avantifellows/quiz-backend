output "ecr_repository_url" {
  description = "ECR repository URL"
  value       = aws_ecr_repository.quiz_backend.repository_url
}

output "alb_dns_name" {
  description = "ALB DNS name (use this to access the API)"
  value       = aws_lb.quiz_backend.dns_name
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = aws_ecs_cluster.quiz_backend.name
}

output "ecs_service_name" {
  description = "ECS service name"
  value       = aws_ecs_service.quiz_backend.name
}

output "cloudwatch_log_group" {
  description = "CloudWatch log group name"
  value       = aws_cloudwatch_log_group.quiz_backend.name
}

output "app_url" {
  description = "Application URL (HTTPS via Cloudflare)"
  value       = "https://${cloudflare_record.quiz_backend.hostname}"
}
