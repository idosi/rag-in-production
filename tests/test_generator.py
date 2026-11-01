from types import SimpleNamespace

from rag.generator import ClaudeGenerator, format_sources, parse_citations
from rag.models import Chunk, RetrievedChunk


def src(n):
    return RetrievedChunk(
        chunk=Chunk("doc", n, f"Heading {n}", f"https://x/#h{n}", f"Heading {n}\n\nBody {n}"),
        score=0.9,
    )


def test_parse_citations_dedupes_and_drops_out_of_range():
    text = "Use Query [2]. Defaults work [1][2]. Also [7]."
    assert parse_citations(text, n_sources=3) == [2, 1]


def test_format_sources_numbers_from_one():
    out = format_sources([src(0), src(1)])
    assert '<source id="1" title="Heading 0"' in out
    assert '<source id="2" title="Heading 1"' in out


class FakeMessages:
    def __init__(self, response):
        self.response = response
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return self.response


def make_generator(response):
    gen = ClaudeGenerator.__new__(ClaudeGenerator)  # skip creating a real client
    gen.model, gen.effort, gen.max_tokens = "claude-opus-5-5", "medium", 1000
    messages = FakeMessages(response)
    gen.client = SimpleNamespace(beta=SimpleNamespace(messages=messages))
    return gen, messages


def response(text, stop_reason="end_turn"):
    return SimpleNamespace(
        content=[SimpleNamespace(type="thinking"), SimpleNamespace(type="text", text=text)],
        stop_reason=stop_reason,
        model="claude-opus-5-5",
        usage=SimpleNamespace(input_tokens=100, output_tokens=20),
    )


def test_generate_sends_sources_and_reads_text_blocks():
    gen, messages = make_generator(response("Use `Query` [1]."))
    answer = gen.generate("How?", [src(0)])
    assert answer.text == "Use `Query` [1]."
    assert answer.cited == [1]
    assert answer.usage["input_tokens"] == 100
    user_msg = messages.kwargs["messages"][0]["content"]
    assert "<sources>" in user_msg and user_msg.endswith("Question: How?")
    assert messages.kwargs["fallbacks"] == "default"


def test_generate_handles_refusal():
    gen, _ = make_generator(response("", stop_reason="refusal"))
    assert "declined" in gen.generate("?", [src(0)]).text


def test_api_key_from_settings_reaches_the_client():
    # .env values live only in Settings, not in os.environ, so the key must be
    # passed to the SDK explicitly.
    gen = ClaudeGenerator("claude-opus-5-5", "medium", 1000, api_key="sk-from-settings")
    assert gen.client.api_key == "sk-from-settings"
