"""What one answer costs, in dollars. Used on every question (guarded.py) and by the evals.

Claude bills per token, with a different price for tokens you send (input) and tokens
it writes (output). `usage` (set in generator.py) holds the model name and both counts,
so the cost of one answer is a multiplication. Ollama models are not in PRICES: free.
"""

# $ per 1M tokens (input, output), first-party API prices as of 2026-10.
# Thinking tokens are billed as output tokens and are included in output_tokens.
# Check https://www.anthropic.com/pricing before trusting these for a real budget.
PRICES: dict[str, tuple[float, float]] = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}


def cost_usd(usage: dict) -> float:
    """Dollar cost of one call from its usage. 0.0 for a model not in PRICES."""
    price_in, price_out = PRICES.get(usage.get("model", ""), (0.0, 0.0))
    return (usage["input_tokens"] * price_in + usage["output_tokens"] * price_out) / 1_000_000


def cost_of(usage: dict | None) -> float:
    """Like cost_usd, but an empty or missing usage (a fake generator, no LLM call) costs 0."""
    if not usage:
        return 0.0
    return cost_usd(usage)
