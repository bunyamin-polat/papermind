"""Rebuild the in-corpus evaluation questions from the current corpus.

**Why this exists.** The 34 hand-written questions were written against a
30,061-paper sample. Growing the corpus to 90,088 did not add papers to that
sample — it drew a *different* one, because each month's slice offset moves with
the per-year quota. 23 of the 26 expected papers vanished and hit-rate@5 read 12%
instead of 92%. Nothing errored, and the number was plausible: "the corpus got
3× bigger, retrieval got harder" is exactly the story you expect. What exposed it
was that the drop was too large to be physically possible.

So questions are generated *from* the corpus now, and this is re-runnable whenever
the corpus changes.

**Two models, on purpose.** Questions are drafted and graded by `gpt-oss:20b`;
answers are produced by `qwen3:30b-a3b`. A generator sharing the answerer's
weights writes questions shaped by its blind spots — easy for exactly the system
under test, and flattering in a way nothing in the output reveals.

**Three gates, because a prompt is a request and a filter is a guarantee.**

1. *Drafted* — the model writes the question a researcher would type while
   looking for the paper.
2. *Does not copy the source* — a question echoing the abstract's wording is a
   keyword lookup for the document those words came from. It scores near 100%
   under every retrieval configuration and flattens the comparison. This one does
   the most work: it rejected 42 of 192 candidates.
3. *Graded* — a second pass checks it is answerable from the abstract, specific,
   and natural. This is the reflection/grading pattern: generate, then critique
   with fresh eyes rather than trusting the first draft.

A fourth gate was written, measured, and deleted; see `MAX_COLD_ANSWER_OVERLAP`
below for what it claimed and why the claim did not survive being checked.

Run:  uv run python -m evaluation.build_questions --target 100
"""

import argparse
import json
import random
import re
import sys
import time
from pathlib import Path

from core.config import settings
from core.llm import complete
from storage.db import connection

QUESTIONS_PATH = Path("evaluation/questions.jsonl")

#: Fixed, so a rebuild samples the same papers and the set is reproducible from
#: the corpus plus this number.
SEED = 20260812

#: Drafts and grades. Deliberately not the model that answers — see the docstring.
#:
#: `qwen3:30b-a3b` was tried here first and could not do the job. It is a thinking
#: model, and on this prompt it thought without ever answering: 3,069 characters of
#: reasoning and an empty response at a 600-token cap, 14,844 and still empty at
#: 3,000, `done_reason=length` both times. Disabling thinking did not fix it — it
#: wrote the reasoning into the answer instead ("We are given a paper titled...").
#: It is a good *answerer*, where long output is expected and the thinking lands in
#: a separate channel, and that is the role it now has.
AUTHOR_MODEL = "gpt-oss:20b"

#: Above this fraction of shared content words, the question is echoing its source.
MAX_SOURCE_OVERLAP = 0.75

#: There used to be a third gate here — "does the answerer already know this
#: without any context?" — and it was **removed after being measured, because it
#: did not work.** Over 144 candidates it rejected 3. Re-probing the survivors
#: found 5 of 40 above its own threshold, so it was not even self-consistent. The
#: cold answers had a median overlap of 0.28 against a threshold of 0.55: the line
#: sat far out in the tail of the distribution it was supposed to cut.
#:
#: The idea is sound and the implementation was not, so the claim goes rather than
#: staying as decoration. A filter that rejects 2% while the documentation says it
#: removes questions the model already knows is worse than no filter — it is a
#: false assurance attached to every number downstream.
_STOP = frozenset("""a an the of and or in on for to with by from as at is are was were be been
being this that these those it its their there here what which who whom how why when where can
could may might will would shall should must do does did not no nor but if then than so such very
more most other some any each both few many own same just don now we our us they them he
she""".split())

_WORD = re.compile(r"[a-z0-9]+")


DRAFT_SYSTEM = """\
You are building a retrieval benchmark for a search engine over AI research papers.

Your job: given one paper, write the single question a researcher would type into \
that search engine **while looking for this paper** — before they had ever read it.

Follow these rules in order of importance:

1. Write from the searcher's side, not the paper's side. The searcher knows the \
problem they have. They do not know this paper's title, its method's name, or the \
words its authors chose.
2. Never reuse the paper's distinctive vocabulary. If the abstract calls something \
"Shredder" or "hierarchical spatio-temporal fusion", the searcher does not know \
those words and cannot type them. Describe the problem plainly instead.
3. The abstract must actually answer it. A question this paper only gestures at is \
a broken benchmark entry.
4. Be specific enough that a generic paper would be a wrong answer. "what is deep \
learning" is useless; so is any question a hundred papers answer equally well.
5. One sentence. Lowercase. No quotation marks, no preamble, no explanation.

Study these:

GOOD — abstract about removing attention heads after training:
  can most attention heads be pruned from a trained transformer without hurting accuracy?
  (a real problem, plainly stated, no borrowed vocabulary)

BAD — same abstract:
  what does this paper show about pruning sixteen attention heads?
  (refers to "this paper" — nobody searches that way)

BAD — same abstract:
  how does structured head pruning affect multi-head self-attention redundancy?
  (lifted the paper's own phrasing; this is a keyword lookup, not a search)

GOOD — abstract about adding learned noise before sending data to a cloud model:
  how can data be obscured before sending it to a cloud service that runs the model?

BAD — same abstract:
  how does Shredder learn noise distributions to protect inference privacy?
  (uses the method's name — a searcher looking for it does not know it exists)

Reply with the question and nothing else."""


DRAFT_USER = """\
Title: {title}

Abstract: {abstract}

Write the search question."""


GRADE_SYSTEM = """\
You are reviewing candidate questions for a retrieval benchmark. You are the last \
check before a bad entry corrupts a measurement, so reject anything doubtful.

Reject the question if ANY of these is true:

- The abstract does not clearly answer it.
- It borrows the paper's distinctive vocabulary — method names, coined terms, or \
title phrasing a searcher could not know in advance.
- It refers to "this paper", "the authors", "the study", or "the proposed method".
- It is so general that many unrelated papers would answer it equally well.
- It is not a natural thing for a person to type into a search box.

Reply with exactly one line:

PASS
or
FAIL: <the single clearest reason, under twelve words>"""


GRADE_USER = """\
Question: {question}

Title: {title}

Abstract: {abstract}

Judge it."""


def content_words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOP and len(w) > 2}


def source_overlap(question: str, source: str) -> float:
    """Fraction of the question's content words that also appear in the source."""
    words = content_words(question)
    return len(words & content_words(source)) / len(words) if words else 1.0


def sample_papers(n: int, seed: int) -> list[dict]:
    """Papers spread evenly across years, so the set is not all recent work."""
    with connection() as conn, conn.cursor() as cur:
        cur.execute("select id, title, abstract, published from papers")
        rows = [
            {"id": r[0], "title": r[1], "abstract": r[2], "year": str(r[3])[:4]}
            for r in cur.fetchall()
        ]

    by_year: dict[str, list[dict]] = {}
    for row in rows:
        by_year.setdefault(row["year"], []).append(row)

    rng = random.Random(seed)
    per_year = max(1, n // len(by_year))
    picked: list[dict] = []
    for year in sorted(by_year):
        pool = by_year[year]
        rng.shuffle(pool)
        picked.extend(pool[:per_year])
    rng.shuffle(picked)
    return picked[:n]


#: A model call that fails is retried this many times before giving up. Local
#: inference drops requests occasionally; one blip should not cost a candidate.
ASK_ATTEMPTS = 3


def _ask(prompt: str, system: str, model: str = AUTHOR_MODEL) -> str | None:
    """One model call, retried. Returns None only if every attempt failed."""
    for attempt in range(ASK_ATTEMPTS):
        try:
            return complete(prompt, system=system, model=model).strip()
        except Exception as error:  # noqa: BLE001
            if attempt == ASK_ATTEMPTS - 1:
                print(f"    model call failed: {type(error).__name__}", file=sys.stderr)
                return None
            time.sleep(2 * (attempt + 1))
    return None


#: Typography this model emits that a keyword index will not match. A non-breaking
#: hyphen looks identical to a hyphen and tokenises differently, so "pseudo‑labels"
#: and "pseudo-labels" become different terms — invisible in every printout, and
#: exactly the kind of mismatch BM25 is being added at step 10 to fix.
_UNICODE_PUNCT = {
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-",
    "‘": "'", "’": "'", "“": '"', "”": '"',
    " ": " ", "…": "...",
}


def normalise(text: str) -> str:
    for source, replacement in _UNICODE_PUNCT.items():
        text = text.replace(source, replacement)
    return " ".join(text.split())


def draft(paper: dict) -> str | None:
    text = _ask(DRAFT_USER.format(**paper), DRAFT_SYSTEM)
    if not text:
        return None
    # Take the first non-empty line: a stray preamble must not become the question.
    line = next((ln.strip().strip('"').strip() for ln in text.splitlines() if ln.strip()), "")
    line = normalise(line)
    return line if line.endswith("?") else None


def grade(question: str, paper: dict) -> tuple[str, str]:
    """Returns (verdict, reason) where verdict is "pass", "fail" or "unavailable".

    Three states rather than two, because the first version collapsed a *failed
    grader call* into a rejection. Both dropped the candidate and both were
    counted as "graded FAIL", so a run in which the grader was simply unreachable
    was indistinguishable from one where it did rigorous work — and the drop
    statistics, which are the only evidence the filters are calibrated, quietly
    became fiction.
    """
    verdict = _ask(GRADE_USER.format(question=question, **paper), GRADE_SYSTEM)
    if verdict is None:
        return "unavailable", "grader could not be reached"
    if verdict.upper().startswith("PASS"):
        return "pass", ""
    return "fail", verdict.split(":", 1)[-1].strip()[:60] or "rejected"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=int, default=100, help="in-corpus questions to keep")
    parser.add_argument("--oversample", type=float, default=2.0, help="drafts per kept question")
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--out", type=Path, default=QUESTIONS_PATH)
    parser.add_argument(
        "--carry-from",
        type=Path,
        default=QUESTIONS_PATH,
        help="existing set to copy the corpus-independent slices from",
    )
    args = parser.parse_args()

    candidates = sample_papers(int(args.target * args.oversample), args.seed)
    print(f"sampled {len(candidates):,} papers")
    print(f"  author  {AUTHOR_MODEL}\n  answerer {settings.ollama_model}")

    dropped = {
        "no draft": 0,
        "copies the source": 0,
        "graded FAIL": 0,
        "grader unreachable": 0,
    }
    reasons: list[str] = []

    # Phased by model, not interleaved per candidate. The two models are 18 GB and
    # 13 GB and this machine has 32 GB, so alternating between them per candidate
    # makes Ollama evict and reload one every single call — the run stops being
    # bounded by inference and starts being bounded by disk.
    print(f"\n[1/2] drafting with {AUTHOR_MODEL}")
    drafted: list[tuple[dict, str]] = []
    seen: set[str] = set()
    for index, paper in enumerate(candidates, 1):
        print(f"  {index}/{len(candidates)}  drafted {len(drafted)}", end="\r")
        question = draft(paper)
        if not question or question.lower() in seen:
            dropped["no draft"] += 1
            continue
        if source_overlap(question, f"{paper['title']} {paper['abstract']}") > MAX_SOURCE_OVERLAP:
            dropped["copies the source"] += 1
            continue
        seen.add(question.lower())
        drafted.append((paper, question))
    print(f"  {len(candidates)}/{len(candidates)}  drafted {len(drafted)}        ")

    print(f"\n[2/2] grading with {AUTHOR_MODEL}")
    kept: list[dict] = []
    for index, (paper, question) in enumerate(drafted, 1):
        if len(kept) >= args.target:
            break
        print(f"  {index}/{len(drafted)}  kept {len(kept)}", end="\r")
        verdict, reason = grade(question, paper)
        if verdict == "unavailable":
            dropped["grader unreachable"] += 1
            continue
        if verdict == "fail":
            dropped["graded FAIL"] += 1
            reasons.append(reason)
            continue
        kept.append({"slice": "in_corpus", "expected": paper["id"], "question": question})
    print(f"  {len(drafted)}/{len(drafted)}  kept {len(kept)}        ")

    print()
    for reason, count in dropped.items():
        print(f"    dropped, {reason}: {count}")
    for reason in reasons[:5]:
        print(f"      grader said: {reason}")
    if dropped["grader unreachable"]:
        print(
            f"\n    WARNING: the grader was unreachable for "
            f"{dropped['grader unreachable']} candidates, which were dropped "
            f"unjudged. The drop statistics above understate what the filters did."
        )

    # The corpus-independent slices survive a corpus change untouched: an
    # out-of-corpus question is about the world, not about which papers were
    # sampled, and a keyword question with no expected id tests behaviour.
    source = args.carry_from
    existing = (
        [json.loads(line) for line in source.read_text().splitlines() if line.strip()]
        if source.exists()
        else []
    )
    carried = [q for q in existing if q["slice"] == "out_of_corpus"]
    carried += [q for q in existing if q["slice"] == "keyword" and not q.get("expected")]
    print(f"    carried over (corpus-independent): {len(carried)}")

    args.out.write_text("\n".join(json.dumps(q) for q in kept + carried) + "\n")
    print(f"\nwrote {len(kept) + len(carried)} questions to {args.out}")
    print("Machine-drafted and machine-graded. Read them before quoting any number.")


if __name__ == "__main__":
    main()
