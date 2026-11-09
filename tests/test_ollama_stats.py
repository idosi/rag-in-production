"""Tests for rag.ollama_tools.ollama_stats (exercise 2g-1)."""

import pytest

from rag.ollama_tools import ollama_stats

# A real-shaped /api/chat reply (stream=False). Ollama gives every duration in
# NANOSECONDS: 1 second = 1_000_000_000 ns.
REPLY = {
    "model": "llama3.1:8b",
    "message": {"role": "assistant", "content": "Use None [1]."},
    "done": True,
    "done_reason": "stop",
    "total_duration": 9_400_000_000,  # 9.4 s, everything
    "load_duration": 3_100_000_000,  # 3.1 s, loading the model into memory
    "prompt_eval_count": 2300,  # tokens read
    "prompt_eval_duration": 2_300_000_000,  # 2.3 s reading the prompt
    "eval_count": 160,  # tokens written
    "eval_duration": 4_000_000_000,  # 4.0 s writing the answer
}


def test_1_durations_are_converted_from_nanoseconds_to_seconds():
    s = ollama_stats(REPLY, num_ctx=8192)
    assert s["load_s"] == 3.1
    assert s["prompt_s"] == 2.3
    assert s["generate_s"] == 4.0
    assert s["total_s"] == 9.4


def test_2_tokens_per_second_counts_only_the_writing_phase():
    # 160 tokens written in 4.0 s -> 40.0 tokens/s (not 160 / 9.4: loading and
    # reading the prompt are not "writing speed").
    assert ollama_stats(REPLY, num_ctx=8192)["tokens_per_s"] == pytest.approx(40.0)


def test_3_missing_fields_count_as_zero_and_never_divide_by_zero():
    s = ollama_stats({"message": {"content": "x"}}, num_ctx=8192)
    assert s["load_s"] == 0.0
    assert s["total_s"] == 0.0
    assert s["tokens_per_s"] == 0.0


def test_4_a_prompt_that_fills_the_whole_context_is_flagged():
    # Ollama does NOT fail on a too-long prompt: it cuts the start and carries on.
    # The only trace is that the prompt token count hits the window size.
    assert ollama_stats(REPLY, num_ctx=8192)["context_full"] is False
    assert ollama_stats({**REPLY, "prompt_eval_count": 8192}, num_ctx=8192)["context_full"] is True


def test_5_an_answer_cut_by_the_length_limit_is_flagged():
    assert ollama_stats(REPLY, num_ctx=8192)["cut_off"] is False
    assert ollama_stats({**REPLY, "done_reason": "length"}, num_ctx=8192)["cut_off"] is True


def test_6_tokens_per_second_uses_the_raw_duration_not_a_rounded_one():
    # 160 tokens in 4 ms: rounding 0.004 s to 0.0 first would give 0 tokens/s.
    assert ollama_stats({"eval_duration": 4_000_000, "eval_count": 160}, 8192)[
        "tokens_per_s"
    ] == pytest.approx(40000.0)


def test_7_total_is_ollamas_own_total_not_the_sum_of_the_three_phases():
    reply = {**REPLY, "total_duration": 9_900_000_000}  # 0.5 s of overhead the phases miss
    assert ollama_stats(reply, 8192)["total_s"] == 9.9
