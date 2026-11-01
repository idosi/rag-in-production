.PHONY: install up down ingest ask api test lint

install:            ## Install dependencies into .venv
	uv sync

up:                 ## Start Postgres + pgvector
	docker compose up -d --wait

down:               ## Stop Postgres (data is kept in a volume)
	docker compose down

ingest:             ## Download the FastAPI docs, chunk, embed and store them
	uv run python -m rag.ingest

ask:                ## Ask a question from the CLI: make ask Q="How do I declare a query parameter?"
	uv run python -m rag.ask "$(Q)"

api:                ## Run the HTTP API on http://localhost:8000 (docs at /docs)
	uv run uvicorn rag.api:app --reload

test:               ## Run the test suite
	uv run pytest -q

lint:
	uv run ruff check src tests
