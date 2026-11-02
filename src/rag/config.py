"""All tunable settings in one place.

Values come from environment variables (or a .env file), so the same code runs
locally, in tests and in the cloud with different settings and no code change.

How a value is chosen, highest priority first:
    1. an environment variable      CHUNK_SIZE=400 make ingest
    2. a line in .env               CHUNK_SIZE=400
    3. the default written below    chunk_size: int = 1200
Names are case-insensitive: the field chunk_size is set by CHUNK_SIZE.
pydantic also converts types and validates: CHUNK_SIZE=abc fails at startup with
a clear error, instead of breaking somewhere deep in the chunker later.
"""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Read .env if it exists; ignore unknown keys in it instead of failing.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Secrets ---
    # SecretStr hides the value when printed or logged ("**********"), so the key
    # doesn't leak into logs by accident. Read it with .get_secret_value().
    anthropic_api_key: SecretStr | None = None

    # --- Storage ---
    # Matches the user/password/db in docker-compose.yml.
    database_url: str = "postgresql://rag:rag@localhost:5432/rag"

    # --- Corpus ---
    # Pinned to a release tag so the corpus never changes under our feet.
    # Reproducible data is what makes evals (step 2) meaningful.
    docs_version: str = "0.162.0"
    docs_cache_dir: str = "data/raw"  # downloaded pages are cached here

    # --- Chunking ---  (changing these re-ingests every page, see store.py)
    chunk_size: int = 1200  # max characters per chunk (~300 tokens)
    chunk_overlap: int = 200  # max characters carried over from the previous chunk

    # --- Embeddings ---  (changing the model requires a full re-ingest)
    # Small, fast, runs locally on CPU. 384-dimensional vectors.
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384  # must match the model's output size

    # --- Retrieval ---
    top_k: int = 5  # chunks given to the LLM per question
    # vector | hybrid | rerank | hybrid_rerank  (see retrieval.py). Chosen by
    # `make eval-retrieval` on 2026-11-01 (docs/learning/02b, section 7):
    #   vector                      hit@5 0.905   8ms
    #   rerank, 30 candidates       hit@5 0.881   620ms   fixed 3, broke 4
    #   rerank, 10 candidates       hit@5 0.952   163ms   fixed 2, broke 0  <- default
    retrieval_mode: Literal["vector", "hybrid", "rerank", "hybrid_rerank"] = "rerank"
    # Pool size for hybrid / rerank before cutting to top_k. Small on purpose: the
    # reranker only reorders the vector search's best 10, so it can't promote a
    # chunk the vector search ranked far down (that is what broke 4 questions at 30).
    candidate_k: int = 10
    rrf_k: int = 60  # RRF constant, see retrieval.rrf
    reranker_model: str = "Xenova/ms-marco-MiniLM-L-6-v2"  # ~80MB cross-encoder, CPU

    # --- Generation ---
    llm_model: str = "claude-sonnet-5-5"  # chosen by make eval-answers, see docs/learning/02c
    llm_effort: str = "medium"  # low | medium | high | xhigh | max
    llm_max_tokens: int = 16000  # cap on reply length; you pay for what's used
    ollama_url: str = "http://localhost:11434"  # local models, used when a model is "ollama:<name>"


@lru_cache  # build Settings once per process and reuse it (reading .env every call is waste)
def get_settings() -> Settings:
    return Settings()
