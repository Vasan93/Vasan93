# GrandmasterAI developer commands.
# `make up` uses Docker Compose. `make dev-*` runs services natively (no Docker).

.PHONY: up down logs dev-backend dev-frontend seed test test-backend test-frontend fmt

up:
	docker compose -f infra/docker-compose.yml up --build

down:
	docker compose -f infra/docker-compose.yml down

logs:
	docker compose -f infra/docker-compose.yml logs -f

dev-backend:
	cd backend && python -m app.bootstrap && uvicorn app.main:app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev

seed:
	cd backend && python -m app.bootstrap --seed

test: test-backend test-frontend

test-backend:
	cd backend && python -m pytest -q

test-frontend:
	cd frontend && npm run test
