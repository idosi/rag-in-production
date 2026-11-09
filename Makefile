.PHONY: install up down ingest ask api test lint eval-retrieval eval-answers docker-build docker-up docker-ingest eval-redteam gcp-build deploy smoke

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

# ---------------------------------------------------------------- Cloud Run (step 3d)
# Full walkthrough: docs/learning/03d-cloud-run-neon.md. One-time setup (project, Neon,
# secrets, service account) is in section 5 there; these targets are the repeatable part.
#
# Region: Frankfurt, the same city as the Neon database (aws-eu-central-1). Every question
# makes 2 to 3 database round trips, so app and database must be close to each other.
GCP_PROJECT ?= $(shell gcloud config get-value project 2>/dev/null)
REGION ?= europe-west3
SERVICE ?= rag-api
# Tagged with the git commit: every running revision says which code it is.
IMAGE ?= $(REGION)-docker.pkg.dev/$(GCP_PROJECT)/rag/$(SERVICE):$(shell git rev-parse --short HEAD)

gcp-build:          ## Build the image in Cloud Build (linux/amd64) and push it to Artifact Registry
	@git diff --quiet HEAD || { echo "Commit first: the image tag is the commit, so it must contain exactly that commit."; exit 1; }
	gcloud builds submit --config cloudbuild.yaml --substitutions _IMAGE=$(IMAGE)

deploy:             ## Deploy the image of the current commit to Cloud Run (run make gcp-build first)
	gcloud run deploy $(SERVICE) \
	  --image $(IMAGE) \
	  --region $(REGION) \
	  --service-account $(SERVICE)@$(GCP_PROJECT).iam.gserviceaccount.com \
	  --set-secrets ANTHROPIC_API_KEY=anthropic-api-key:latest,DATABASE_URL=database-url:latest,API_KEYS=api-keys:latest \
	  --set-env-vars DAILY_BUDGET_USD=1 \
	  --memory 2Gi --cpu 1 --cpu-boost \
	  --concurrency 8 --min-instances 0 --max-instances 2 \
	  --timeout 60 \
	  --startup-probe httpGet.path=/health,periodSeconds=5,timeoutSeconds=3,failureThreshold=24 \
	  --liveness-probe httpGet.path=/health,periodSeconds=30,timeoutSeconds=3,failureThreshold=3 \
	  --allow-unauthenticated

URL ?= $(shell gcloud run services describe $(SERVICE) --region $(REGION) --format 'value(status.url)' 2>/dev/null)
smoke:              ## Check the deployed service end to end: API_KEY=... make smoke
	scripts/smoke.sh "$(URL)"
