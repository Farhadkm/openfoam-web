# Deployment

## Local (Docker Compose)

```bash
docker compose up --build -d    # detached
docker compose down             # stop
docker compose down -v          # stop + remove volumes (jobs + mongo)
```

## AWS dev

Full procedure: [deploy/aws/README.md](../../deploy/aws/README.md).

**Summary:**

1. `terraform apply` in `deploy/aws/terraform/`
2. Configure GitHub secrets: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `DEV_PUBLIC_HOST`, `DEV_EC2_INSTANCE_ID`
3. Optional: `gemini_secret_arn` for Vertex credentials on EC2
4. Push to `develop` branch → images to ECR → SSM redeploy on instance

**Compose file on host:** `docker-compose.aws-dev.yml` with `.env` generated at bootstrap (`ECR_REGISTRY`, public host substitution).

## Image list (ECR)

frontend, backend, trame-viewer — see Terraform `aws_ecr_repository.services` (runner uses the backend image).

## Rollback

On EC2: pull previous image tag or re-run workflow from last known-good commit; restart compose. No blue/green in dev stack.
