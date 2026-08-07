"""Ask the corpus a question and see what comes back. Retrieval only — the
generated answer arrives at step 5.

Run:  uv run python -m scripts.ask "what is attention"
"""

import sys

from retrieval.retriever import DEFAULT_K, search


def main() -> None:
    question = " ".join(sys.argv[1:]) or "what is an attention mechanism"
    results = search(question, k=DEFAULT_K)

    print(f"\n{question!r}\n")
    for i, r in enumerate(results, 1):
        print(f"{i}. [{r.distance:.3f}] {' '.join(r.title.split())}")
        print(f"   {r.url}")
        print(f"   {' '.join(r.abstract.split())[:150]}...\n")


if __name__ == "__main__":
    main()
