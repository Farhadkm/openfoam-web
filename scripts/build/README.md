# Build scripts

## Local images

```bash
docker compose build
```

## AWS dev (CI)

GitHub Actions `.github/workflows/deploy-dev.yml` builds **linux/amd64** and pushes to ECR on push to `dev`.

Manual equivalent (example):

```bash
docker build --platform linux/amd64 -t openfoam-web-dev-backend ./backend
```

See workflow file for exact tags and registry naming.
