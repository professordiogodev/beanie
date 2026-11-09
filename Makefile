.PHONY: help install install-dev run run-one test test-integration lint format check env load clean

help:
	@echo "Targets:"
	@echo "  make install           Install runtime dependencies"
	@echo "  make install-dev       Install runtime + test + lint dependencies"
	@echo "  make run               Start all five services on localhost (gateway :8000 ... notifications :8004)"
	@echo "  make run-one S=menu    Start one service (gateway|menu|orders|payments|notifications)"
	@echo "  make load              Send orders to the gateway (see scripts/loadgen.py --help)"
	@echo "  make test              Unit tests with coverage (no services needed)"
	@echo "  make test-integration  Tests against a real PostgreSQL (needs DATABASE_URL)"
	@echo "  make lint              ruff check and format check"
	@echo "  make format            ruff format and import sorting"
	@echo "  make check             lint + tests (what CI runs)"
	@echo "  make env               Create .env from .env.example"
	@echo "  make clean             Remove caches"

install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements-dev.txt

run:
	python scripts/run_all.py

run-one:
	python -m beanie $(S)

load:
	python scripts/loadgen.py

test:
	pytest -m "not integration" --cov

test-integration:
	pytest -m integration -v

lint:
	ruff check beanie tests scripts
	ruff format --check beanie tests scripts

format:
	ruff check --fix beanie tests scripts
	ruff format beanie tests scripts

check: lint test

env:
	@test -f .env && echo ".env already exists" || (cp .env.example .env && echo "created .env")

clean:
	rm -rf .pytest_cache .ruff_cache .coverage htmlcov
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
