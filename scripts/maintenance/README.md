# Maintenance scripts

## Reset local data

```bash
docker compose down -v
```

Removes `jobs_data` and `mongo_data` volumes.

## Clean Docker artifacts

```bash
docker system prune -f
docker volume ls    # inspect orphaned volumes (e.g. after AWS volume rename)
```

## AWS dev cost control

```bash
cd deploy/aws/terraform
terraform destroy   # when dev host not needed
```

## Credential rotation

- **GCP:** replace `backend/credentials/key.json` locally; on AWS update Secrets Manager secret referenced by `gemini_secret_arn` and redeploy/re-bootstrap.
