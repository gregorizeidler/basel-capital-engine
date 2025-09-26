# Basel Capital Engine Makefile

.PHONY: help install dev-install test lint format clean build docker run-api run-dashboard docs

# Default target
help:
	@echo "Basel Capital Engine - Available Commands:"
	@echo ""
	@echo "Development:"
	@echo "  install       Install the package in production mode"
	@echo "  dev-install   Install the package in development mode"
	@echo "  test          Run tests"
	@echo "  test-fast     Run tests excluding slow ones"
	@echo "  test-cov      Run tests with coverage report"
	@echo "  lint          Run linting checks"
	@echo "  format        Format code with black and ruff"
	@echo "  type-check    Run mypy type checking"
	@echo "  clean         Clean up build artifacts"
	@echo ""
	@echo "Docker:"
	@echo "  docker-build  Build Docker images"
	@echo "  docker-run    Run all services with docker-compose"
	@echo "  docker-api    Run only the API service"
	@echo "  docker-dash   Run only the dashboard service"
	@echo "  docker-dev    Run development environment"
	@echo "  docker-stop   Stop all services"
	@echo "  docker-clean  Clean up Docker resources"
	@echo ""
	@echo "Application:"
	@echo "  run-api       Run FastAPI server locally"
	@echo "  run-dashboard Run Streamlit dashboard locally"
	@echo "  run-jupyter   Start Jupyter Lab"
	@echo ""
	@echo "Documentation:"
	@echo "  docs          Build documentation"
	@echo "  docs-serve    Serve documentation locally"

# Installation
install:
	pip install -e .

dev-install:
	pip install -e ".[dev,api,app,cli,all]"
	pre-commit install

# Testing
test:
	pytest tests/ -v

test-fast:
	pytest tests/ -v -m "not slow"

test-cov:
	pytest tests/ --cov=src/basileia --cov-report=html --cov-report=term

test-properties:
	pytest tests/test_properties.py -v --hypothesis-show-statistics

# Code quality
lint:
	ruff check src/ tests/ api/ app/
	mypy src/ --ignore-missing-imports

format:
	black src/ tests/ api/ app/
	ruff check --fix src/ tests/ api/ app/

type-check:
	mypy src/ --ignore-missing-imports

# Cleanup
clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf build/
	rm -rf dist/
	rm -rf htmlcov/
	rm -rf .coverage
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/

# Docker commands
docker-build:
	docker-compose build

docker-run:
	docker-compose up -d

docker-api:
	docker-compose up -d basel-api

docker-dash:
	docker-compose up -d basel-dashboard

docker-dev:
	docker-compose --profile dev up -d

docker-prod:
	docker-compose --profile prod --profile db --profile cache up -d

docker-stop:
	docker-compose down

docker-clean:
	docker-compose down -v --rmi all
	docker system prune -f

# Local application runs
run-api:
	cd api && uvicorn main:app --reload --host 0.0.0.0 --port 8000

run-dashboard:
	streamlit run app/dashboard.py

run-jupyter:
	jupyter lab --ip=0.0.0.0 --port=8888 --no-browser

# Documentation
docs:
	@echo "Building documentation..."
	@echo "Technical guide available at docs/technical_guide.md"
	@echo "API documentation available at http://localhost:8000/docs when API is running"

docs-serve:
	@echo "Starting documentation server..."
	@echo "Open http://localhost:8000/docs for API documentation"
	@echo "Technical guide: docs/technical_guide.md"

# Package building
build:
	python -m build

build-wheel:
	python -m build --wheel

build-sdist:
	python -m build --sdist

# Publishing (requires authentication)
publish-test:
	python -m twine upload --repository testpypi dist/*

publish:
	python -m twine upload dist/*

# Database operations (when using PostgreSQL)
db-init:
	docker-compose --profile db up -d postgres
	sleep 5
	docker-compose exec postgres psql -U basel_user -d basel_capital -f /docker-entrypoint-initdb.d/init.sql

db-reset:
	docker-compose --profile db down postgres
	docker volume rm basileia3_postgres_data
	make db-init

# Backup and restore
backup-data:
	mkdir -p backups
	tar -czf backups/basel_data_$(shell date +%Y%m%d_%H%M%S).tar.gz data/

restore-data:
	@echo "Available backups:"
	@ls -la backups/
	@echo "Use: tar -xzf backups/[backup_file] to restore"

# Performance testing
perf-test:
	python -m pytest tests/ -k "performance" -v

# Security scanning
security-check:
	safety check
	bandit -r src/

# Pre-commit hooks
pre-commit:
	pre-commit run --all-files

# Environment setup
setup-dev:
	python -m venv venv
	source venv/bin/activate && pip install --upgrade pip
	source venv/bin/activate && make dev-install
	@echo "Development environment ready!"
	@echo "Activate with: source venv/bin/activate"

# Quick start for new users
quickstart: setup-dev
	@echo ""
	@echo "🏦 Basel Capital Engine - Quick Start Complete!"
	@echo ""
	@echo "Next steps:"
	@echo "1. Activate environment: source venv/bin/activate"
	@echo "2. Run tests: make test"
	@echo "3. Start API: make run-api"
	@echo "4. Start dashboard: make run-dashboard"
	@echo "5. Open notebooks: make run-jupyter"
	@echo ""
	@echo "For Docker: make docker-run"
	@echo "For help: make help"

# CI/CD helpers
ci-test:
	pytest tests/ --junitxml=test-results.xml --cov=src/basileia --cov-report=xml

ci-build:
	docker build -t basel-capital-engine:latest .

# Version management
version:
	@python -c "import src.basileia; print(f'Basel Capital Engine v{src.basileia.__version__}')"

# Example data generation
generate-examples:
	python -c "
from src.basileia.simulator.portfolio import PortfolioGenerator, BankSize;
import json;
gen = PortfolioGenerator(seed=42);
portfolio, capital = gen.generate_bank_portfolio(BankSize.MEDIUM, 'Example Bank');
data = {'portfolio': portfolio.model_dump(), 'capital': capital.model_dump()};
with open('data/example_portfolio.json', 'w') as f: json.dump(data, f, indent=2, default=str);
print('Example data generated: data/example_portfolio.json')
"

# Monitoring and health checks
health-check:
	@echo "Checking service health..."
	@curl -f http://localhost:8000/health || echo "API not responding"
	@curl -f http://localhost:8501/_stcore/health || echo "Dashboard not responding"

# Load testing
load-test:
	@echo "Running load tests..."
	@echo "Install locust first: pip install locust"
	@echo "Then run: locust -f tests/load_test.py --host=http://localhost:8000"
