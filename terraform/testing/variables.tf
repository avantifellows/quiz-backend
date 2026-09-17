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

variable "mongo_db_name" {
  description = "MongoDB database name"
  type        = string
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

variable "cloudflare_api_key" {
  description = "Cloudflare Global API key"
  type        = string
  sensitive   = true
}

variable "cloudflare_email" {
  description = "Cloudflare account email"
  type        = string
}

variable "cloudflare_zone_name" {
  description = "Cloudflare zone name (e.g. avantifellows.org)"
  type        = string
}

variable "cms_service_endpoint" {
  description = "Base URL of the new CMS (nex-gen-cms) service API, used for test ingest (e.g. https://staging-new-cms.avantifellows.org)"
  type        = string
}

variable "cms_service_token" {
  description = "Bearer token for the new CMS service API. Must match the CMS's CMS_SERVICE_TOKEN for this environment, or /quiz/from-cms will 401."
  type        = string
  sensitive   = true
}

variable "backend_image" {
  description = "Exact backend image reference. Capture the service's current SHA tag or digest before every infrastructure apply."
  type        = string
  validation {
    condition     = can(regex("(:[0-9a-f]{40}|@sha256:[0-9a-f]{64})$", var.backend_image))
    error_message = "Use a full commit-SHA image tag or sha256 digest, never latest."
  }
}

variable "cache_enabled" {
  description = "Enable Redis reads/writes only after staging validation."
  type        = bool
  default     = false
}

variable "cache_namespace" {
  description = "Redis key namespace."
  type        = string
  default     = "v1"
  validation {
    condition     = can(regex("^[A-Za-z0-9_-]+$", var.cache_namespace))
    error_message = "Use a nonempty namespace containing letters, numbers, underscores or hyphens."
  }
}

variable "redis_max_connections" {
  description = "Redis pool limit per backend worker; tune from measured load."
  type        = number
  default     = 10
  validation {
    condition     = var.redis_max_connections >= 1 && floor(var.redis_max_connections) == var.redis_max_connections
    error_message = "Redis pool limit must be a positive integer."
  }
}
