"""Command-line way to ask a question. Handy for trying things without the API.

HOW TO RUN
    make ask Q="How do I make a query parameter optional?"
    (same as: uv run python -m rag.ask "How do I make a query parameter optional?")

Prerequisites: `make up` (database running) and `make ingest` (index built).
The flow itself is in pipeline.py: RAGPipeline.ask.
"""

import sys

from rag.pipeline import build_pipeline


def main() -> None:
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        sys.exit('usage: python -m rag.ask "How do I declare a query parameter?"')
    # build_pipeline loads the model and connects to the DB (slow, once);
    # .ask runs the 4 steps for this question (see pipeline.py).
    answer = build_pipeline().ask(sys.argv[1])

    # Print the answer, then every source we gave the model. The * marks the ones
    # the answer actually cited. Reading the scores is the best way to build an
    # intuition for retrieval: which questions get high scores, which get poor ones?

    print(answer.text, "\n")
    print("Retrieved sources (* = cited):")
    for i, s in enumerate(answer.sources, start=1):
        mark = "*" if i in answer.cited else " "
        print(f" {mark}[{i}] {s.score:.3f}  {s.chunk.heading}\n        {s.chunk.url}")
    if answer.usage:
        print(f"\nTokens: {answer.usage['input_tokens']} in / {answer.usage['output_tokens']} out")


if __name__ == "__main__":
    main()
