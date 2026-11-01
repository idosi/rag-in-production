"""python -m rag.ask "your question" """

import sys

from rag.pipeline import build_pipeline


def main() -> None:
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        sys.exit('usage: python -m rag.ask "How do I declare a query parameter?"')
    answer = build_pipeline().ask(sys.argv[1])

    print(answer.text, "\n")
    print("Retrieved sources (* = cited):")
    for i, s in enumerate(answer.sources, start=1):
        mark = "*" if i in answer.cited else " "
        print(f" {mark}[{i}] {s.score:.3f}  {s.chunk.heading}\n        {s.chunk.url}")
    if answer.usage:
        print(f"\nTokens: {answer.usage['input_tokens']} in / {answer.usage['output_tokens']} out")


if __name__ == "__main__":
    main()
