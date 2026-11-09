"""Tests for exercise 2g-2. Do not edit; make them pass by editing my_preflight.py.

Run:   uv run pytest exercises/ollama_preflight -q
"""

import httpx
import pytest

from exercises.ollama_preflight.my_preflight import OllamaNotReady, missing_models, preflight

# What GET /api/tags returns: the models already downloaded (`ollama list`).
TAGS = {
    "models": [
        {"name": "llama3.1:8b", "size": 4_920_000_000},
        {"name": "llama3.2:latest", "size": 2_020_000_000},
    ]
}


def test_1_nothing_missing_when_every_model_is_downloaded():
    assert missing_models(TAGS, ["llama3.1:8b", "llama3.2:latest"]) == []


def test_2_missing_models_are_returned_in_the_order_they_were_asked_for():
    wanted = ["qwen2.5:7b", "llama3.1:8b", "gemma3:4b"]
    assert missing_models(TAGS, wanted) == ["qwen2.5:7b", "gemma3:4b"]


def test_3_a_name_without_a_tag_means_latest():
    # `ollama pull llama3.2` stores it as "llama3.2:latest".
    assert missing_models(TAGS, ["llama3.2"]) == []


def test_4_the_size_tag_must_match():
    # 8b is downloaded, 70b is not: a different model, ~40GB more.
    assert missing_models(TAGS, ["llama3.1:70b"]) == ["llama3.1:70b"]


def client_answering(handler) -> httpx.Client:
    return httpx.Client(base_url="http://x", transport=httpx.MockTransport(handler))


def test_5_preflight_asks_the_server_and_is_quiet_when_all_is_well():
    seen = []

    def handler(request):
        seen.append((request.method, request.url.path))
        return httpx.Response(200, json=TAGS)

    assert preflight(client_answering(handler), ["llama3.1:8b"]) is None
    assert seen == [("GET", "/api/tags")]


def test_6_preflight_tells_you_the_exact_command_for_each_missing_model():
    client = client_answering(lambda request: httpx.Response(200, json=TAGS))
    with pytest.raises(OllamaNotReady) as err:
        preflight(client, ["qwen2.5:7b", "gemma3:4b"])
    assert "ollama pull qwen2.5:7b" in str(err.value)
    assert "ollama pull gemma3:4b" in str(err.value)


def test_7_server_not_running_becomes_a_clear_error_not_a_stack_trace():
    def handler(request):
        raise httpx.ConnectError("Connection refused")

    with pytest.raises(OllamaNotReady) as err:
        preflight(client_answering(handler), ["llama3.1:8b"])
    assert "ollama serve" in str(err.value)
