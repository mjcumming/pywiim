.PHONY: help format lint typecheck test clean install dev-install check prepare-release release

help:
	@echo "Available targets:"
	@echo "  make format      - Format code with Black and isort"
	@echo "  make lint        - Lint code with Ruff"
	@echo "  make typecheck   - Type check with mypy"
	@echo "  make test        - Run tests with pytest"
	@echo "  make check       - Run all CI checks (format + lint + test + coverage >= 55%)"
	@echo "  make prepare-release - Run cached Linux release checks for the committed candidate"
	@echo "  make release     - Publish a version already merged to main via GitHub Actions"
	@echo "                    Usage: make release VERSION=3.0.1"
	@echo "  make clean       - Clean build artifacts"
	@echo "  make install     - Install package"
	@echo "  make dev-install - Install package with dev dependencies"

format:
	@echo "Formatting code with Black and isort..."
	black pywiim tests
	isort pywiim tests

lint:
	@echo "Linting code with Ruff..."
	ruff check pywiim tests

typecheck:
	@echo "Type checking with mypy..."
	mypy pywiim

check:
	@echo "Running all CI checks..."
	@echo "1. Checking code formatting with Black..."
	black pywiim tests --check --diff || (echo "❌ Code formatting failed! Run 'make format' to fix." && exit 1)
	@echo "✅ Code formatting OK"
	@echo "2. Checking import sorting..."
	isort pywiim tests --check-only --diff || (echo "❌ Import sorting failed! Run 'make format' to fix." && exit 1)
	@echo "✅ Import sorting OK"
	@echo "3. Linting with Ruff..."
	ruff check pywiim tests || (echo "❌ Linting failed!" && exit 1)
	@echo "✅ Linting OK"
	@echo "4. Type checking with mypy..."
	mypy pywiim || (echo "❌ Type check failed!" && exit 1)
	@echo "✅ Type check OK"
	@echo "5. Running unit tests with coverage..."
	@if python -c "import xdist" 2>/dev/null; then \
		pytest tests/ -m "not integration" -x --tb=short -q -n auto --cov=pywiim --cov-report=term --cov-fail-under=55; \
	else \
		pytest tests/ -m "not integration" -x --tb=short -q --cov=pywiim --cov-report=term --cov-fail-under=55; \
	fi
	@echo "✅ All checks passed (including coverage >= 55%)!"

test:
	@echo "Running tests with pytest..."
	pytest

test-cov:
	@echo "Running tests with coverage..."
	pytest --cov=pywiim --cov-report=html --cov-report=term

prepare-release:
	python scripts/prepare_release.py

clean:
	@echo "Cleaning build artifacts..."
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	find . -type d -name __pycache__ -exec rm -r {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

install:
	pip install -e .

dev-install:
	pip install -e ".[dev]"
	@echo "Optional staged-file checks: pre-commit install"

# Publish the version already reviewed and merged to main.
release:
ifndef VERSION
	$(error VERSION is required. Usage: make release VERSION=3.0.1)
endif
	@bash scripts/release.sh "$(VERSION)"

