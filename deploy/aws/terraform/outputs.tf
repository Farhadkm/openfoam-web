output "ecr_registry" {
  description = "ECR login URL prefix (account.dkr.ecr.region.amazonaws.com)."
  value       = local.ecr_registry
}

output "ecr_repository_urls" {
  description = "Map of service name to ECR repository URL (no tag)."
  value       = { for k, v in aws_ecr_repository.services : k => v.repository_url }
}

output "dev_instance_id" {
  description = "EC2 instance id for SSM / GitHub secret DEV_EC2_INSTANCE_ID."
  value       = aws_instance.dev.id
}

output "dev_public_dns" {
  description = "Public DNS for the dev host (set GitHub secret DEV_PUBLIC_HOST to this value)."
  value       = aws_instance.dev.public_dns
}

output "config_bucket" {
  description = "S3 bucket holding docker-compose.aws-dev.yml (updated by terraform apply)."
  value       = aws_s3_bucket.config.id
}

output "aws_region" {
  value = var.aws_region
}
