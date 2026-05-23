# AWS dev environment (Forge)

This folder defines a **development-only** stack: ECR repositories, an S3 bucket for the compose file, and a single **EC2** host running Docker Compose (same topology as local `docker-compose.yml`, including Docker-in-Docker for `forge-runner`).

There is **no production** Terraform or workflow in this repository.

## Credentials (same pattern as SimavAI)

Use the same AWS account access model as [SimavAI](https://github.com) dev deploys:

1. Create an IAM user or role with permission to push to ECR, run SSM on the dev instance, and read the config bucket.
2. In GitHub → **Settings → Secrets and variables → Actions**, add to the environment **`dev`** (or repository secrets):

| Secret | Purpose |
|--------|---------|
| `AWS_ACCESS_KEY_ID` | Same style as SimavAI dev workflow |
| `AWS_SECRET_ACCESS_KEY` | Same style as SimavAI dev workflow |
| `DEV_PUBLIC_HOST` | After first `terraform apply`, set to `dev_public_dns` output (e.g. `ec2-54-…compute.amazonaws.com`) — used as Next.js public API / Trame / WS URLs at **image build** time |
| `DEV_EC2_INSTANCE_ID` | From `terraform output -raw dev_instance_id` — used to SSM-redeploy after images push |

Optional:

| Secret | Purpose |
|--------|---------|
| `GEMINI_IMAGE_MODEL` | Override image model tag for AI Dockerfile build (defaults in Dockerfile) |

**Vertex / chatbot credentials:** the AI container expects a real **GCP service account JSON** (field `"type": "service_account"`, plus `project_id`, `private_key`, etc.). Set Terraform variable `gemini_secret_arn` to an AWS **Secrets Manager** secret whose **SecretString** is that whole JSON document. On first boot the instance writes it to `backend/credentials/key.json`. If `gemini_secret_arn` is unset, bootstrap writes **`{}`**, which is **not** valid Google credentials — Vertex then fails with *“Type is None, expected one of …”* and the bot will not work until you add a proper secret and re-bootstrap or replace the file on the host.

Example (create secret once, then set `gemini_secret_arn` in `terraform.tfvars` and `terraform apply`; new instances or SSM re-run of user-data steps pick it up):

```bash
aws secretsmanager create-secret --name forge-web-dev-gemini-sa \
  --secret-string file:///path/to/your-service-account.json
```

## One-time: provision infra

```bash
cd deploy/aws/terraform
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars if needed

terraform init
terraform apply
```

Copy outputs into GitHub secrets `DEV_PUBLIC_HOST` and `DEV_EC2_INSTANCE_ID`, then push the `develop` branch to trigger image build + deploy.

**Order matters:** first `terraform apply` creates ECR repos (empty). Then run the **Deploy dev** workflow (or push to `develop`) to build and push images. If the instance already booted before images existed, use **Actions → Re-run** after images exist, or SSM:

```bash
aws ssm start-session --target "$(terraform output -raw dev_instance_id)"
sudo -i
cd /opt/forge-web
source .env
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin "$ECR_REGISTRY"
docker compose --env-file .env -f docker-compose.aws-dev.yml pull
docker compose --env-file .env -f docker-compose.aws-dev.yml up -d
```

## GitHub Actions

Workflow: `.github/workflows/deploy-dev.yml`  
Trigger: **push** to branch `develop` only (no `main` / prod deploy).

It configures AWS with `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`, builds **linux/amd64** images, pushes to the `forge-web-dev-*` ECR repos, then runs an SSM command on `DEV_EC2_INSTANCE_ID` to pull and restart compose.

## CORS

The compose file substitutes `__PUBLIC_HOST__` with the instance public hostname at boot. `DEV_PUBLIC_HOST` in CI must match that host so browser-built URLs align with the backend CORS list.

## Jobs volume (solver runs)

The backend and Trame store cases under the Compose volume `jobs_data` (mounted at `/jobs`). The runner must pass **the same Docker volume name** into child solver containers (`JOBS_VOLUME_NAME`). If those names differ, the solver container can see an empty `case/` directory and fail with `./Allrun: No such file or directory` even though the ZIP uploaded correctly. This repo pins the host volume name to `forge-jobs-data` in `docker-compose.aws-dev.yml` so backend, runner, and child containers stay aligned. After changing volume naming, restart compose on the host; you may remove orphaned volumes (for example `forge_jobs_data`) with `docker volume ls` / `docker volume rm` if you no longer need them.

## Costs

Dev uses a single EC2 instance (default `t3.xlarge`) and five ECR repos. Shut down or `terraform destroy` when not needed.
