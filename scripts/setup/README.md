# Setup scripts

Document first-time setup here. Prefer standard commands over duplicated shell scripts.

## Local

```bash
cp .env.example .env          # optional overrides
mkdir -p backend/credentials       # place key.json for Vertex (do not commit)
docker compose up --build
```

## AWS dev (one-time)

```bash
cd deploy/aws/terraform
cp terraform.tfvars.example terraform.tfvars
terraform init && terraform apply
```

Then configure GitHub secrets per `deploy/aws/README.md`.
