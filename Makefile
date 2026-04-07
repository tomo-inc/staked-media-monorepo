BE_DIR := apps/backend
FE_DIR := apps/browser-extension
BE_CONFIG ?= config.json

.PHONY: lint format typecheck check test build \
        be-lint be-format be-format-check be-typecheck be-check be-test be-run \
        fe-lint fe-format fe-format-check fe-typecheck fe-check fe-build fe-test \
        fe-install

# ── Backend ──────────────────────────────────────────────

be-lint:
	cd $(BE_DIR) && uv run --extra dev ruff check app/ tests/

be-format:
	cd $(BE_DIR) && uv run --extra dev ruff format app/ tests/

be-format-check:
	cd $(BE_DIR) && uv run --extra dev ruff format --check app/ tests/

be-typecheck:
	cd $(BE_DIR) && uv run --extra dev pyright app/

be-check: be-lint be-format-check be-typecheck

be-test:
	cd $(BE_DIR) && uv run --extra dev pytest tests/ -q

be-run:
	cd $(BE_DIR) && uv run python -m app.run -c $(abspath $(BE_CONFIG)) --reload

# ── Frontend ─────────────────────────────────────────────

fe-install:
	cd $(FE_DIR) && npm install

fe-lint:
	cd $(FE_DIR) && npx biome check --error-on-warnings src/ tests/

fe-format:
	cd $(FE_DIR) && npx biome format --write src/ tests/

fe-format-check:
	cd $(FE_DIR) && npx biome format src/ tests/

fe-typecheck:
	cd $(FE_DIR) && npx tsc --noEmit -p tsconfig.json

fe-build:
	cd $(FE_DIR) && npm run build

fe-check: fe-lint fe-format-check fe-typecheck

fe-test:
	cd $(FE_DIR) && npm run test:compiled

# ── All ──────────────────────────────────────────────────

lint: be-lint fe-lint

format: be-format fe-format

typecheck: be-typecheck fe-typecheck

check: be-check fe-check

build: fe-build

test: be-test fe-test
