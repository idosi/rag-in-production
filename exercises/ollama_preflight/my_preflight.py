"""EXERCISE 2g-2: fail in 1 second, not after 10 minutes.

Run the tests:   uv run pytest exercises/ollama_preflight -q
They all fail now. Make them pass one by one, and commit after each green test.

WHY
    `make eval-answers` first retrieves sources for all 47 questions, then answers
    with Claude, and only THEN reaches the Ollama model. If you forgot
    `ollama pull qwen2.5:7b`, or Ollama isn't running, you find out minutes later
    as an httpx stack trace (404 or "Connection refused"), after paying for Claude.

    A preflight check asks the server once, at the start: "which models do you
    have?" (GET /api/tags, the same list `ollama list` prints) and stops with the
    exact command to fix it. Same idea as `make ingest` refusing an empty index.

THE SPEC
    class OllamaNotReady(Exception)

    missing_models(tags, wanted) -> list[str]
        tags    the JSON of GET /api/tags: {"models": [{"name": "llama3.1:8b"}, ...]}
        wanted  model names as the user wrote them, e.g. ["llama3.2", "qwen2.5:7b"]
        returns the wanted names that are NOT downloaded, in the order of `wanted`.
        A name without a tag means ":latest" (llama3.2 == llama3.2:latest).

    preflight(client, wanted) -> None
        client  an httpx.Client whose base_url is the Ollama server
        Calls GET /api/tags. Returns None if everything is there.
        Missing models   -> raise OllamaNotReady with "ollama pull <name>" per model
        Server not up    -> raise OllamaNotReady that mentions "ollama serve"
                            (httpx raises httpx.ConnectError; don't let it leak)

HINTS (open one at a time, only when stuck)
    1. One helper fixes the tag problem for both sides:
       def full_name(name): return name if ":" in name else name + ":latest"
    2. Put the downloaded names in a set (fast `in`), but loop over `wanted` to keep
       its order.
    3. httpx.HTTPError is the parent of ConnectError, timeouts AND
       HTTPStatusError (from response.raise_for_status()). One except catches all.
    4. `raise OllamaNotReady(...) from e` keeps the original error attached, so the
       real cause is still visible when debugging.
    5. "\n".join(f"  ollama pull {m}" for m in missing) builds a copy-pasteable list.

THINK ABOUT (we discuss after the tests are green)
    - Why check at the START of the run and not inside OllamaGenerator.generate()?
    - In production (step 3d), what is the equivalent check? (hint: /health and
      "ready" vs "alive")
    - Should preflight also pull the missing model automatically? What could go
      wrong with that on a CI runner or a laptop on a train?
"""

import httpx


class OllamaNotReady(Exception):
    """Ollama is not running, or a model we need is not downloaded."""


def missing_models(tags: dict, wanted: list[str]) -> list[str]:
    if "models" not in tags:
        raise ValueError("tags JSON does not contain 'models' key")
    downloaded = {full_name(m["name"]) for m in tags["models"]}
    return [name for name in wanted if full_name(name) not in downloaded]


def preflight(client: httpx.Client, wanted: list[str]) -> None:
    try:
        response = client.get("/api/tags", timeout=10.0)
        response.raise_for_status()
        tags = response.json()
    except (httpx.HTTPError, ValueError) as not_ready:
        raise OllamaNotReady("Ollama server is not running. Please start it with 'ollama serve'.") from not_ready

    missing = missing_models(tags, wanted)
    if missing:
        raise OllamaNotReady(
            "The following models are missing:\n" + "\n".join(f"  ollama pull {m}" for m in missing)
        )
    
def full_name(name: str) -> str:
    return name if ":" in name else name + ":latest"