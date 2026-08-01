UV ?= uv

.PHONY: sync lint typecheck test check up down

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
