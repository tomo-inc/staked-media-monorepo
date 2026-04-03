BE_DIR := apps/backend
FE_DIR := apps/browser-extension

.PHONY: lint format typecheck check test build \
        be-lint be-format be-typecheck be-check be-test \
        fe-lint fe-format fe-typecheck fe-check fe-build fe-test \
        fe-install

# ── Backend ──────────────────────────────────────────────

be-lint:
	cd $(BE_DIR) && ruff check app/ tests/

be-format:
	cd $(BE_DIR) && ruff format app/ tests/

be-typecheck:
	cd $(BE_DIR) && pyright app/

be-check: be-lint be-format be-typecheck

be-test:
	cd $(BE_DIR) && python -m pytest tests/ -q

# ── Frontend ─────────────────────────────────────────────

fe-install:
	cd $(FE_DIR) && npm install

fe-lint:
	cd $(FE_DIR) && npx biome check src/ tests/

fe-format:
	cd $(FE_DIR) && npx biome format --write src/ tests/

fe-typecheck:
	cd $(FE_DIR) && npx tsc --noEmit -p tsconfig.json

fe-build:
	cd $(FE_DIR) && npm run build

fe-check: fe-lint fe-typecheck

fe-test: fe-build
	cd $(FE_DIR) && node --test tests/*.test.js

# ── All ──────────────────────────────────────────────────

lint: be-lint fe-lint

format: be-format fe-format

typecheck: be-typecheck fe-typecheck

check: be-check fe-check

build: fe-build

test: be-test fe-test
