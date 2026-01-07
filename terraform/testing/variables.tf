variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "ap-south-1"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "testing"
}

variable "mongo_auth_credentials" {
  description = "MongoDB connection URI"
  type        = string
  sensitive   = true
}

variable "app_port" {
  description = "Port the application runs on"
  type        = number
  default     = 8000
}

variable "task_cpu" {
  description = "CPU units for ECS task (1024 = 1 vCPU)"
  type        = number
  default     = 1024
}

variable "task_memory" {
  description = "Memory for ECS task in MB"
  type        = number
  default     = 2048
}

variable "desired_count" {
  description = "Number of ECS tasks to run"
  type        = number
  default     = 1
}
