.PHONY: help install test lint format clean run deploy

help:
	@echo "Available commands:"
	@echo "  make install    - Install dependencies"
	@echo "  make test       - Run tests"
	@echo "  make lint       - Run linting"
	@echo "  make format     - Format code"
	@echo "  make clean      - Clean build artifacts"
	@echo "  make run        - Run locally"
	@echo "  make deploy     - Deploy to Cloud Run"

install:
	pip install -r requirements.txt
	pip install -r requirements-dev.txt

test:
	pytest tests/ -v

test-unit:
	pytest tests/unit/ -v -m unit

test-integration:
	pytest tests/integration/ -v -m integration

lint:
	flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
	flake8 . --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics
	mypy agents/ config/ tools/ utils/ --ignore-missing-imports

format:
	black .
	isort .

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	rm -rf htmlcov
	rm -rf dist
	rm -rf build

run:
	python main.py

run-dev:
	ENVIRONMENT=development LOG_LEVEL=DEBUG python main.py

docker-build:
	docker build -t workspace-adk -f docker/Dockerfile .

docker-run:
	docker run -it --env-file .env workspace-adk

deploy:
	gcloud run deploy workspace-adk \
		--source . \
		--platform managed \
		--region us-central1 \
		--allow-unauthenticated

setup-db-postgres:
	psql $$DATABASE_URL < migrations/001_create_sessions_table.sql

logs:
	gcloud logging read "resource.type=cloud_run_revision" --limit 50

metrics:
	@echo "Fetching metrics..."
	@curl -s http://localhost:8080/metrics | python -m json.tool
