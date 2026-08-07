"""Turning retrieved papers into a prompt, and the answer back into citations.

**The model never writes an identifier.** It cites sources by their position in the
list it was given — `[1]`, `[2]` — and those positions are mapped back to real
papers by code that already knows which paper is which. A model asked to emit
`arXiv:2406.06538` will eventually emit a plausible identifier that does not exist,
and there is no way to tell from the text that it invented one. Positions cannot be
hallucinated into something real: `[9]` in a list of five is detectably wrong, and
gets dropped.
"""

import re

from retrieval.retriever import Result

# The model is told to emit this exact sentence when the sources do not answer the
# question. An exact string is testable; "say you don't know" is not.
REFUSAL = "The provided sources do not answer this question."

SYSTEM = f"""You answer questions about AI research using only the sources given to you.

Rules:
- Use only the numbered sources below. Never use anything you know from elsewhere.
- Cite every claim with the source number in square brackets, like [1] or [2][3].
- If the sources do not contain the answer, reply with exactly this sentence and \
nothing else: {REFUSAL}
- Be concise. Three or four sentences is usually enough.
- Never invent a source number that is not in the list."""

CITATION = re.compile(r"\[(\d+)\]")


def build(question: str, results: list[Result]) -> str:
    sources = "\n\n".join(
        f"[{i}] {' '.join(r.title.split())}\n{' '.join(r.abstract.split())}"
        for i, r in enumerate(results, 1)
    )
    return f"SOURCES\n{sources}\n\nQUESTION\n{question}\n\nANSWER"


def cited_indices(answer: str, n_sources: int) -> list[int]:
    """The source numbers the answer actually used, in order, deduplicated.

    Out-of-range numbers are dropped rather than raising: the model inventing `[9]`
    for five sources is a citation that points nowhere, and the honest handling is
    to not show it. It is counted separately by `invalid_citations`.
    """
    seen, valid = set(), []
    for match in CITATION.findall(answer):
        i = int(match)
        if 1 <= i <= n_sources and i not in seen:
            seen.add(i)
            valid.append(i)
    return valid


def invalid_citations(answer: str, n_sources: int) -> list[int]:
    """Source numbers the model produced that do not exist. Should always be empty;
    if it is not, the prompt is not holding and that is worth knowing."""
    return sorted({int(m) for m in CITATION.findall(answer) if not 1 <= int(m) <= n_sources})


def is_refusal(answer: str) -> bool:
    return REFUSAL.lower() in answer.strip().lower()
