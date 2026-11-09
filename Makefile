.PHONY: install up down ingest ask api test lint eval-retrieval eval-answers docker-build docker-up docker-ingest eval-redteam

install:            ## Install dependencies into .venv
	uv sync

up:                 ## Start Postgres + pgvector
	docker compose up -d --wait

down:               ## Stop Postgres and the API container (data is kept in volumes)
	docker compose --profile app down

ingest:             ## Download the FastAPI docs, chunk, embed and store them
	uv run python -m rag.ingest

ask:                ## Ask a question from the CLI: make ask Q="How do I declare a query parameter?"
	uv run python -m rag.ask "$(Q)"

api:                ## Run the HTTP API on http://localhost:8000 (docs at /docs)
	uv run uvicorn rag.api:app --reload

MODES ?= vector,hybrid,rerank,hybrid_rerank
eval-retrieval:     ## Measure search quality per retrieval mode (free by default; the rewrite modes call Haiku): make eval-retrieval MODES=vector,rerank,rewrite_rerank
	uv run python -m rag.evals.retrieval --modes $(MODES)

ANSWER_MODELS ?= claude-haiku-5-5,claude-sonnet-5-5,claude-opus-5-5
LIMIT ?= 0
ONLY ?=
eval-answers:       ## Grade answers per model with an LLM judge (COSTS MONEY, asks first): make eval-answers ANSWER_MODELS=claude-haiku-5-5 LIMIT=5 (or ONLY=unanswerable)
	uv run python -m rag.evals.answers --models $(ANSWER_MODELS) --limit $(LIMIT) --only "$(ONLY)"

eval-redteam:       ## Try prompt-injection attacks on the real model (costs a few cents)
	uv run python -m rag.evals.red_team

test:               ## Run the test suite
	uv run pytest -q

lint:
	uv run ruff check src tests

docker-build:       ## Build the API image
	docker compose --profile app build

docker-up:          ## Run Postgres + the API in containers (http://localhost:8000/docs)
	docker compose --profile app up -d --build --wait

docker-ingest:      ## Fill the index from inside the container (first time, or after docs change)
	docker compose --profile app run --rm api python -m rag.ingest
