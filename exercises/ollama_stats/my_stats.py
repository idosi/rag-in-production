"""EXERCISE 2g-1: what did Ollama spend its time on?

Run the tests:   uv run pytest exercises/ollama_stats -q
They all fail now. Make them pass one by one, and commit after each green test.

WHY
    With Claude, "latency" is one number and we can't see inside it. Ollama runs on
    YOUR machine and tells you exactly where the time went, in every reply:

        load_duration         loading the model into RAM/GPU (only on a cold start)
        prompt_eval_duration  reading our ~2,500-token prompt (the 5 sources)
        eval_duration         writing the answer, token by token

    Without this split, a benchmark lies: the first question pays a 5-20 s model
    load, so "llama is slow" may really be "llama was cold". And a slow laptop
    without a GPU spends most of its time READING the prompt, not writing.

THE SPEC
    ollama_stats(data, num_ctx) -> dict
        data      the JSON of one /api/chat reply (stream=False)
        num_ctx   the context window we asked for (8192 in OllamaGenerator)
    returns:
        load_s, prompt_s, generate_s, total_s
                      seconds, rounded to 2 decimals. Ollama sends NANOSECONDS.
        tokens_per_s  eval_count / eval_duration in seconds, rounded to 1 decimal
        context_full  True when prompt_eval_count >= num_ctx (Ollama silently cut
                      the start of the prompt, where our rules are)
        cut_off       True when done_reason == "length" (the answer was cut)
    A missing field counts as 0. Never raise ZeroDivisionError.

HINTS (open one at a time, only when stuck)
    1. 1 second = 1_000_000_000 ns. A module constant NS = 1_000_000_000 reads better
       than a magic number repeated 5 times.
    2. data.get("load_duration", 0) handles "missing".
    3. A tiny inner helper, def sec(key): ..., avoids writing the same line 4 times.
    4. Division by zero: compute the seconds first, then
       `x / secs if secs else 0.0`.
    5. Round tokens_per_s from the UNROUNDED seconds, or 160 tokens in 0.004 s
       becomes 160 / 0.0 after rounding.

THINK ABOUT (we discuss after the tests are green)
    - Run 1 of a benchmark has load_s = 8.0, runs 2..47 have 0.0. What do you do with
      run 1 when you report p50 latency? And when you report p95?
    - On your Mac, which is bigger: prompt_s or generate_s? Predict before you run.
      What would change that balance: top_k=10, or longer answers?
    - Claude's latency has no load_s. Why not, and what is the cloud equivalent of a
      cold start? (hint: Cloud Run, step 3d)
"""


def ollama_stats(data: dict, num_ctx: int) -> dict:
    raise NotImplementedError("your code here")
