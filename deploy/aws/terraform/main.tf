locals {
  name_prefix  = "${var.project}-${var.environment}"
  account_id   = data.aws_caller_identity.current.account_id
  ecr_registry = "${local.account_id}.dkr.ecr.${var.aws_region}.amazonaws.com"
}

data "aws_vpc" "selected" {
  count   = var.vpc_id != "" ? 1 : 0
  id      = var.vpc_id
  default = false
}

data "aws_vpc" "default" {
  count   = var.vpc_id == "" ? 1 : 0
  default = true
}

locals {
  vpc_id = var.vpc_id != "" ? data.aws_vpc.selected[0].id : data.aws_vpc.default[0].id
}

data "aws_subnets" "pick" {
  filter {
    name   = "vpc-id"
    values = [local.vpc_id]
  }
}

locals {
  subnet_id = var.subnet_id != "" ? var.subnet_id : tolist(data.aws_subnets.pick.ids)[0]
}

resource "aws_ecr_repository" "services" {
  for_each = toset([
    "frontend",
    "backend",
    "ai",
    "trame-viewer",
    "openfoam-runner",
  ])
  name                 = "${local.name_prefix}-${each.key}"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "services" {
  for_each   = aws_ecr_repository.services
  repository = each.value.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 15 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 15
      }
      action = { type = "expire" }
    }]
  })
}

resource "aws_s3_bucket" "config" {
  bucket        = "${local.name_prefix}-config-${local.account_id}"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "config" {
  bucket                  = aws_s3_bucket.config.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_object" "compose" {
  bucket = aws_s3_bucket.config.id
  key    = "docker-compose.aws-dev.yml"
  source = "${path.module}/../../../docker-compose.aws-dev.yml"
  etag   = filemd5("${path.module}/../../../docker-compose.aws-dev.yml")
}

data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ec2" {
  name               = "${local.name_prefix}-ec2-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

data "aws_iam_policy_document" "ec2_policy" {
  statement {
    sid = "EcrPull"
    actions = [
      "ecr:GetAuthorizationToken",
    ]
    resources = ["*"]
  }
  statement {
    sid = "EcrPullRepos"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage",
    ]
    resources = [for r in aws_ecr_repository.services : r.arn]
  }
  statement {
    sid = "S3ConfigRead"
    actions = [
      "s3:GetObject",
      "s3:ListBucket",
    ]
    resources = [
      aws_s3_bucket.config.arn,
      "${aws_s3_bucket.config.arn}/*",
    ]
  }
  dynamic "statement" {
    for_each = var.gemini_secret_arn != "" ? [1] : []
    content {
      sid = "SecretsGeminiRead"
      actions = [
        "secretsmanager:GetSecretValue",
      ]
      resources = [var.gemini_secret_arn]
    }
  }
}

resource "aws_iam_role_policy" "ec2" {
  name   = "${local.name_prefix}-ec2-inline"
  role   = aws_iam_role.ec2.id
  policy = data.aws_iam_policy_document.ec2_policy.json
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.ec2.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "ec2" {
  name = "${local.name_prefix}-ec2-profile"
  role = aws_iam_role.ec2.name
}

resource "aws_security_group" "app" {
  name        = "${local.name_prefix}-sg"
  description = "Dev: web + API + trame + AI"
  vpc_id      = local.vpc_id

  ingress {
    description = "Frontend"
    from_port   = 3000
    to_port     = 3000
    protocol    = "tcp"
    cidr_blocks = var.allowed_ingress_cidrs
  }
  ingress {
    description = "Backend API"
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = var.allowed_ingress_cidrs
  }
  ingress {
    description = "Trame viewer"
    from_port   = 8090
    to_port     = 8090
    protocol    = "tcp"
    cidr_blocks = var.allowed_ingress_cidrs
  }
  ingress {
    description = "AI WebSocket"
    from_port   = 8081
    to_port     = 8081
    protocol    = "tcp"
    cidr_blocks = var.allowed_ingress_cidrs
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${local.name_prefix}-sg"
  }
}

data "aws_ssm_parameter" "al2023" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

locals {
  user_data = <<-EOT
    #!/bin/bash
    set -euxo pipefail
    dnf update -y
    dnf install -y docker aws-cli
    systemctl enable docker && systemctl start docker
    usermod -aG docker ec2-user || true
    mkdir -p /usr/local/lib/docker/cli-plugins
    curl -fsSL "https://github.com/docker/compose/releases/download/v2.32.4/docker-compose-linux-x86_64" -o /usr/local/lib/docker/cli-plugins/docker-compose
    chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
    mkdir -p /opt/openfoam-web/ai/credentials
    IMDS_TOKEN=$(curl -sS -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
    PUBLIC_HOST=$(curl -sS -H "X-aws-ec2-metadata-token: $IMDS_TOKEN" http://169.254.169.254/latest/meta-data/public-hostname)
    aws configure set default.region ${var.aws_region}
    aws s3 cp "s3://${aws_s3_bucket.config.id}/docker-compose.aws-dev.yml" /opt/openfoam-web/docker-compose.aws-dev.yml
    sed -i "s|__PUBLIC_HOST__|$PUBLIC_HOST|g" /opt/openfoam-web/docker-compose.aws-dev.yml
    %{if var.gemini_secret_arn != ""}
    aws secretsmanager get-secret-value --secret-id "${var.gemini_secret_arn}" --query SecretString --output text > /opt/openfoam-web/ai/credentials/key.json
    %{else}
    echo "{}" > /opt/openfoam-web/ai/credentials/key.json
    %{endif}
    echo "ECR_REGISTRY=${local.ecr_registry}" > /opt/openfoam-web/.env
    echo "GOOGLE_CLOUD_PROJECT_ID=composite-dream-427518-b8" >> /opt/openfoam-web/.env
    chown -R ec2-user:ec2-user /opt/openfoam-web
    TOKEN=$(aws ecr get-login-password --region ${var.aws_region})
    echo "$TOKEN" | docker login --username AWS --password-stdin ${local.ecr_registry}
    cd /opt/openfoam-web
    export ECR_REGISTRY=${local.ecr_registry}
    export PUBLIC_HOST="$PUBLIC_HOST"
    docker compose --env-file .env -f docker-compose.aws-dev.yml pull || true
    docker compose --env-file .env -f docker-compose.aws-dev.yml up -d || true
  EOT
}

resource "aws_instance" "dev" {
  ami                         = data.aws_ssm_parameter.al2023.value
  instance_type               = var.ec2_instance_type
  subnet_id                   = local.subnet_id
  vpc_security_group_ids      = [aws_security_group.app.id]
  iam_instance_profile        = aws_iam_instance_profile.ec2.name
  user_data_base64            = base64encode(local.user_data)
  user_data_replace_on_change = true

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  root_block_device {
    volume_size = 80
    volume_type = "gp3"
  }

  tags = {
    Name = "${local.name_prefix}-dev-host"
  }
}
