"""All tunable settings in one place.

Values come from environment variables (or a .env file), so the same code runs
locally, in tests and in the cloud with different settings and no code change.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Storage ---
    database_url: str = "postgresql://rag:rag@localhost:5432/rag"

    # --- Corpus ---
    # Pinned to a release tag so the corpus never changes under our feet.
    # Reproducible data is what makes evals (step 2) meaningful.
    docs_version: str = "0.162.0"
    docs_cache_dir: str = "data/raw"

    # --- Chunking ---
    chunk_size: int = 1200  # max characters per chunk (~300 tokens)
    chunk_overlap: int = 200  # max characters carried over from the previous chunk

    # --- Embeddings ---
    # Small, fast, runs locally on CPU. 384-dimensional vectors.
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384

    # --- Retrieval ---
    top_k: int = 5

    # --- Generation ---
    llm_model: str = "claude-opus-5-5"
    llm_effort: str = "medium"  # low | medium | high | xhigh | max
    llm_max_tokens: int = 16000


@lru_cache
def get_settings() -> Settings:
    return Settings()
