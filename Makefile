.PHONY: up down logs ps build reset openapi

openapi:
	./scripts/openapi/export_and_merge.sh

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

ps:
	docker compose ps

build:
	docker compose build

reset:
	docker compose down -v
