# Infrastructure

AWS dev infrastructure and deployment assets live under **`deploy/`** (not a separate Terraform root at repo top level).

| Path | Contents |
|------|----------|
| `deploy/aws/terraform/` | ECR, S3, EC2, IAM, user-data bootstrap |
| `deploy/aws/README.md` | Credentials, apply order, GitHub secrets |
| `docker-compose.aws-dev.yml` | Production-like dev stack on EC2 |

See [docs/operations/deployment.md](../docs/operations/deployment.md).
