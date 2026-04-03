.PHONY: lint format typecheck check test

lint:
	ruff check app/ tests/

format:
	ruff format app/ tests/

typecheck:
	pyright app/

check: lint typecheck
	ruff format --check app/ tests/

test:
	python -m pytest tests/ -q
