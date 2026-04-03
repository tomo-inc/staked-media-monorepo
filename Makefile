.PHONY: lint format typecheck check test

lint:
	cd apps/backend && ruff check app/ tests/

format:
	cd apps/backend && ruff format app/ tests/

typecheck:
	cd apps/backend && pyright app/

check: lint typecheck
	cd apps/backend && ruff format --check app/ tests/

test:
	cd apps/backend && python -m pytest tests/ -q
