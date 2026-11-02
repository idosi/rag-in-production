# rag-in-production

A Retrieval-Augmented Generation (RAG) service that answers questions about the [FastAPI](https://fastapi.tiangolo.com) documentation, with citations. Built step by step, with every design decision explained, as a learning and portfolio project.

## How it works

```mermaid
flowchart LR
  A[FastAPI docs] --> B[Loader] --> C[Chunker] --> D[Embedder] --> E[(Postgres + pgvector)]
  Q[Question] --> QE[Embedder] --> S[Vector search] --> F[RRF fusion]
  Q --> K[Keyword search] --> F
  F --> X[Cross-encoder rerank] --> G[Claude] --> R[Answer + citations]
  E --> S
  E --> K
```

| Layer | Choice | Why |
|---|---|---|
| Corpus | 48 FastAPI docs pages (43 tutorial + overview pages), pinned to `0.162.0` | Small enough to understand, stable enough to evaluate |
| Chunking | Markdown-structure aware, ~1200 chars, heading path prefix | Never splits code examples; every chunk knows its context |
| Embeddings | `BAAI/bge-small-en-v1.5` via fastembed (local) | No API key, no per-call cost |
| Store | Postgres 16 + pgvector, HNSW index | One database for text, metadata and vectors |
| Retrieval | `vector`, `hybrid` (+ Postgres full-text, RRF), `rerank` (cross-encoder), or both | Each idea measured separately on the golden set before it becomes the default |
| Generation | Claude, sources-only prompt with `[n]` citations | Grounded answers that can be verified |
| API | FastAPI | `POST /ask`, `GET /health` |

## Quick start

Requires Docker, [uv](https://docs.astral.sh/uv/) and an [Anthropic API key](https://console.anthropic.com).

```bash
cp .env.example .env      # add ANTHROPIC_API_KEY
make install
make up                   # Postgres + pgvector
make ingest               # download, chunk, embed, store
make ask Q="How do I make a query parameter optional?"
make api                  # http://localhost:8000/docs
make eval-retrieval        # search quality per retrieval mode, no LLM calls
make eval-answers          # answer quality + cost per model, LLM judge (costs ~$4)
make test
```

## Roadmap

- [x] **Step 1: Foundations.** End-to-end RAG with citations ([explanation](docs/learning/01-foundations.md))
- [ ] **Step 2: Measured quality.**
  - [x] 2a: golden set (47 questions) and retrieval evals ([explanation](docs/learning/02a-retrieval-evals.md))
  - [x] 2b: hybrid search and reranking, four modes compared ([explanation](docs/learning/02b-hybrid-search-rerank.md))
  - [x] 2c: answer evals (LLM-as-judge) and model comparison ([explanation](docs/learning/02c-answer-evals.md))
  - [ ] 2f: overview pages in the corpus + 6 overview/unanswerable questions (built, re-measure pending) ([explanation](docs/learning/02f-corpus-overview-pages.md))
- [ ] **Step 3: Production.** Tracing, cost tracking, caching, auth, rate limiting, prompt-injection defenses, Docker, CI, cloud deploy
- [ ] **Step 4: Write-up.** Architecture, results, and the trade-off behind every decision
