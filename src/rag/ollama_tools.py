"""Helpers for running a local Ollama model (step 2g). Written by Ido as TDD exercises.

Two jobs:
  ollama_stats  what did Ollama spend its time on? (loading, reading, writing), plus
                the two silent failures: a prompt cut by the context window, and an
                answer cut by the length limit.
  preflight     at the START of an eval, check that the server runs and the models are
                downloaded, and fail with the exact fix command instead of an httpx
                stack trace minutes later.
"""

import httpx

NS = 1_000_000_000  # Ollama reports every duration in nanoseconds


def ollama_stats(data: dict, num_ctx: int) -> dict:
    """Turn the JSON of one /api/chat reply into readable numbers.

    data     the reply (stream=False)
    num_ctx  the context window we asked for
    A missing field counts as 0 and nothing divides by zero.
    """

    def sec(key: str) -> float:
        return round(data.get(key, 0) / NS, 2)

    eval_count = data.get("eval_count", 0)
    # Divide by the RAW duration: rounding 4 ms to 0.0 first would give 0 tokens/s.
    gen_raw = data.get("eval_duration", 0) / NS
    return {
        "load_s": sec("load_duration"),  # loading the model into memory (cold start)
        "prompt_s": sec("prompt_eval_duration"),  # reading our ~2,500-token prompt
        "generate_s": sec("eval_duration"),  # writing the answer
        "total_s": sec("total_duration"),  # Ollama's own total, more than the sum above
        "tokens_per_s": round(eval_count / gen_raw, 1) if gen_raw else 0.0,
        # Ollama silently cuts the START of a too-long prompt (where our rules are).
        # The only trace is a prompt token count that reaches the window size.
        "context_full": data.get("prompt_eval_count", 0) >= num_ctx,
        "cut_off": data.get("done_reason") == "length",
    }


class OllamaNotReady(Exception):
    pass


def full_name(name: str) -> str:
    """A model name without a tag means ":latest" (llama3.2 == llama3.2:latest)."""
    return name if ":" in name else name + ":latest"


def missing_models(tags: dict, wanted: list[str]) -> list[str]:
    """The wanted models that are not downloaded, in the order they were asked for."""
    if "models" not in tags:
        raise ValueError("tags JSON does not contain 'models' key")
    downloaded = {full_name(m["name"]) for m in tags["models"]}
    return [name for name in wanted if full_name(name) not in downloaded]


def preflight(client: httpx.Client, wanted: list[str]) -> None:
    """Ask the server (GET /api/tags, the same list as `ollama list`) once, up front."""
    try:
        response = client.get("/api/tags", timeout=10.0)
        response.raise_for_status()
        tags = response.json()
        missing = missing_models(tags, wanted)
    except (httpx.HTTPError, ValueError) as not_ready:
        # JSONDecodeError and a missing "models" key are ValueErrors too.
        raise OllamaNotReady(
            "Ollama server is not running. Please start it with 'ollama serve'."
        ) from not_ready
    if missing:
        raise OllamaNotReady(
            "The following models are missing:\n" + "\n".join(f"  ollama pull {m}" for m in missing)
        )
