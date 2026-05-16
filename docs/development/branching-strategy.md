# Branching strategy

## Branches

| Branch | Purpose |
|--------|---------|
| `main` (or default) | Stable application source; no automated prod deploy in this repo |
| `dev` | Triggers AWS dev image build and EC2 redeploy via GitHub Actions |

## Workflow

1. Feature work on topic branches from default branch
2. Merge to `dev` when ready to validate on shared AWS dev EC2
3. Use pull requests for review when working in a team

## CI

- **deploy-dev.yml** — on push to `dev`: build linux/amd64 images, push to ECR, SSM restart on `DEV_EC2_INSTANCE_ID`

Infrastructure changes: apply Terraform from `deploy/aws/terraform/` before relying on new AWS resources.
