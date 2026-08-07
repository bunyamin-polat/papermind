"""Retrieve, ground, generate — the whole RAG path in one function.

Run:  uv run python -m retrieval.answer "what is an attention mechanism"
"""

import re
import sys
import time
from dataclasses import dataclass

from core import llm
from retrieval import prompt
from retrieval.retriever import DEFAULT_K, Result, search

# qwen3 and similar reasoning models emit a visible chain of thought. It is not
# part of the answer and must not reach the user or the citation parser.
THINK = re.compile(r"<think>.*?</think>\s*", re.S)


@dataclass
class Answer:
    question: str
    text: str
    sources: list[Result]  # only the ones actually cited, in citation order
    retrieved: list[Result]  # everything that went into the prompt
    refused: bool
    invalid_citations: list[int]
    latency_ms: float


def ask(question: str, k: int = DEFAULT_K) -> Answer:
    started = time.perf_counter()

    retrieved = search(question, k=k)
    raw = llm.complete(prompt.build(question, retrieved), system=prompt.SYSTEM)
    text = THINK.sub("", raw).strip()

    cited = prompt.cited_indices(text, len(retrieved))
    return Answer(
        question=question,
        text=text,
        sources=[retrieved[i - 1] for i in cited],
        retrieved=retrieved,
        refused=prompt.is_refusal(text),
        invalid_citations=prompt.invalid_citations(text, len(retrieved)),
        latency_ms=(time.perf_counter() - started) * 1000,
    )


def main() -> None:
    question = " ".join(sys.argv[1:]) or "what is an attention mechanism"
    answer = ask(question)

    print(f"\nQ: {answer.question}\n")
    print(answer.text)

    if answer.sources:
        print("\nSources:")
        for i, source in enumerate(answer.sources, 1):
            print(f"  [{i}] {' '.join(source.title.split())}")
            print(f"      {source.url}")
    elif not answer.refused:
        print("\n(no sources cited — the answer is ungrounded)")

    if answer.invalid_citations:
        print(f"\n! invented source numbers: {answer.invalid_citations}")
    print(f"\n{answer.latency_ms / 1000:.1f}s")


if __name__ == "__main__":
    main()
