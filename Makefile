.PHONY: install up down ingest ask api test lint eval-retrieval eval-answers

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

MODES ?= vector,hybrid,rerank,hybrid_rerank
eval-retrieval:     ## Measure search quality per retrieval mode (no LLM calls, free): make eval-retrieval MODES=vector,rerank
	uv run python -m rag.evals.retrieval --modes $(MODES)

ANSWER_MODELS ?= claude-haiku-5-5,claude-sonnet-5-5,claude-opus-5-5
LIMIT ?= 0
eval-answers:       ## Grade answers per model with an LLM judge (COSTS MONEY, asks first): make eval-answers ANSWER_MODELS=claude-haiku-5-5 LIMIT=5
	uv run python -m rag.evals.answers --models $(ANSWER_MODELS) --limit $(LIMIT)

test:               ## Run the test suite
	uv run pytest -q

lint:
	uv run ruff check src tests
