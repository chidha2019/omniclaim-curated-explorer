.PHONY: install dev test build contract check-assets
install:
	python3 -m venv .venv
	.venv/bin/pip install --require-hashes -r backend/requirements-dev.lock
	cd frontend && npm ci --ignore-scripts --no-audit --no-fund
dev:
	npm run dev
test:
	cd backend && ../.venv/bin/python -m pytest --cov=app --cov-fail-under=85
	cd frontend && npm test
build:
	cd frontend && npm run build
contract:
	.venv/bin/python tools/export_openapi.py
	cd frontend && npm run contract
check-assets:
	.venv/bin/python tools/check_assets.py
