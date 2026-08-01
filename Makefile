UV ?= uv

.PHONY: sync lint typecheck test check up down demo prod-config prod-up prod-smoke

sync:
	$(UV) sync --frozen

lint:
	$(UV) run ruff check .

typecheck:
	$(UV) run mypy src

test:
	$(UV) run pytest -q

check: lint typecheck test

up:
	docker compose up -d --build

down:
	docker compose down

demo:
	./scripts/demo.sh

prod-config:
	./scripts/validate-production-env.sh .env.production
	docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml config --quiet

prod-up: prod-config
	docker compose --env-file .env.production -f docker-compose.yml -f docker-compose.prod.yml up -d --build

prod-smoke:
	./scripts/smoke-test.sh
