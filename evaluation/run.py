"""Step 4 — the evaluation harness. Everything after this can be justified with a
number instead of an impression.

Reports per-question results by default, not only aggregates. Eight defects have
been found in this project so far and every one of them produced plausible-looking
output; a harness that prints `hit-rate 0.82` and nothing else is exactly the kind
of instrument that would hide the ninth.

Run:  uv run python -m evaluation.run
      uv run python -m evaluation.run --k 1 3 5 10   # sweep k
      uv run python -m evaluation.run --quiet        # aggregates only
"""

import argparse
import json
import statistics as st
import time
from dataclasses import dataclass
from pathlib import Path

from retrieval.retriever import search

QUESTIONS_PATH = Path(__file__).parent / "questions.jsonl"


@dataclass
class Outcome:
    question: str
    slice: str
    expected: str | None
    rank: int | None  # 1-based position of the expected paper, None if absent
    top_distance: float
    top_title: str
    latency_ms: float


def load_questions(path: Path = QUESTIONS_PATH) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def evaluate(questions: list[dict], k: int) -> list[Outcome]:
    # Warm up before timing anything. The first call loads the SentenceTransformer,
    # which took 8.3 seconds and landed in p95 as if it were query latency. A
    # measurement that includes one-time setup is measuring the wrong thing.
    search("warm up the model and the connection", k=1)

    outcomes = []
    for q in questions:
        started = time.perf_counter()
        results = search(q["question"], k=k)
        latency = (time.perf_counter() - started) * 1000

        rank = None
        if q["expected"]:
            ids = [r.paper_id for r in results]
            rank = ids.index(q["expected"]) + 1 if q["expected"] in ids else None

        outcomes.append(
            Outcome(
                question=q["question"],
                slice=q["slice"],
                expected=q["expected"],
                rank=rank,
                top_distance=results[0].distance if results else float("nan"),
                top_title=results[0].title if results else "",
                latency_ms=latency,
            )
        )
    return outcomes


def hit_rate(outcomes: list[Outcome]) -> float:
    scored = [o for o in outcomes if o.expected]
    return sum(o.rank is not None for o in scored) / len(scored) if scored else 0.0


def mrr(outcomes: list[Outcome]) -> float:
    """Mean reciprocal rank — rewards putting the right paper first, not merely
    somewhere in the list. Hit-rate alone cannot tell rank 1 from rank 5."""
    scored = [o for o in outcomes if o.expected]
    return sum(1 / o.rank if o.rank else 0 for o in scored) / len(scored) if scored else 0.0


def report(outcomes: list[Outcome], k: int, quiet: bool) -> None:
    print(f"\n{'=' * 78}\nk = {k}\n{'=' * 78}")

    for slice_name in ("in_corpus", "keyword", "out_of_corpus"):
        rows = [o for o in outcomes if o.slice == slice_name]
        if not rows:
            continue

        scored = [o for o in rows if o.expected]
        header = f"\n[{slice_name}]  {len(rows)} questions"
        if scored:
            header += f"   hit-rate@{k} {hit_rate(rows):.0%}   MRR {mrr(rows):.3f}"
        print(header)

        if quiet:
            continue

        for o in rows:
            if o.expected:
                mark = f"rank {o.rank}" if o.rank else "MISS"
            else:
                mark = "—"  # nothing to hit; distance is the signal
            print(f"  {mark:<8} d={o.top_distance:.3f}  {o.question[:56]}")
            if o.expected and not o.rank:
                print(f"           got: {' '.join(o.top_title.split())[:60]}")

    distances = {
        name: [o.top_distance for o in outcomes if o.slice == name]
        for name in ("in_corpus", "out_of_corpus")
    }
    print("\n[distance of the top hit]  in-corpus vs out-of-corpus")
    for name, values in distances.items():
        if values:
            print(
                f"  {name:<15} min {min(values):.3f}   "
                f"median {st.median(values):.3f}   max {max(values):.3f}"
            )

    if all(distances.values()):
        gap = min(distances["out_of_corpus"]) - max(distances["in_corpus"])
        verdict = "separable" if gap > 0 else f"OVERLAP of {abs(gap):.3f}"
        print(f"  separation: {verdict}")

    latencies = [o.latency_ms for o in outcomes]
    print(f"\n[latency]  median {st.median(latencies):.0f} ms   p95 {max(latencies):.0f} ms")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--k", type=int, nargs="+", default=[5])
    parser.add_argument("--quiet", action="store_true", help="aggregates only")
    args = parser.parse_args()

    questions = load_questions()
    for k in args.k:
        report(evaluate(questions, k), k, args.quiet)


if __name__ == "__main__":
    main()
