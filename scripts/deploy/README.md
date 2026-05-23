# Deploy scripts

## Local

```bash
docker compose up --build -d
docker compose down
```

## AWS dev

Automated: push to branch `develop`.

Manual on EC2 (after SSM login):

```bash
cd /opt/forge-web
source .env
aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin "$ECR_REGISTRY"
docker compose --env-file .env -f docker-compose.aws-dev.yml pull
docker compose --env-file .env -f docker-compose.aws-dev.yml up -d
```

Full context: [deploy/aws/README.md](../../deploy/aws/README.md).
