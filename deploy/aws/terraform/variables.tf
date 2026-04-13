variable "aws_region" {
  type        = string
  description = "AWS region (SimavAI dev uses us-east-1)."
  default     = "us-east-1"
}

variable "project" {
  type        = string
  description = "Short project prefix for resource names."
  default     = "openfoam-web"
}

variable "environment" {
  type        = string
  description = "Environment name suffix; must be dev for this stack."
  default     = "dev"
}

variable "ec2_instance_type" {
  type        = string
  description = "Instance type for the single dev host (Docker + DinD runner)."
  default     = "t3.xlarge"
}

variable "allowed_ingress_cidrs" {
  type        = list(string)
  description = "CIDRs allowed to reach app ports (3000, 8000, 8090, 8081). Tighten for real use."
  default     = ["0.0.0.0/0"]
}

variable "vpc_id" {
  type        = string
  description = "Optional: use a specific VPC. Leave empty to use the default VPC."
  default     = ""
}

variable "subnet_id" {
  type        = string
  description = "Optional: single subnet for the EC2 instance. Leave empty to pick the first default-VPC subnet."
  default     = ""
}

variable "gemini_secret_arn" {
  type        = string
  description = "Optional: Secrets Manager secret ARN (string or JSON key) for Gemini service account JSON. Bootstrapped onto the instance before compose up."
  default     = ""
}
