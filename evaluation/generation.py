"""Step 5 — measuring the generated answer, not just the retrieval behind it.

Retrieval hit-rate says the right paper was found. It does not say the answer used
it, cited it, or existed at all. These are the end-to-end numbers:

  answered        — in-corpus questions that produced an answer rather than a refusal
  cited expected  — answers that cite the paper the question was written from
  invalid cites   — source numbers the model invented (should be zero)
  refused         — out-of-corpus questions correctly declined

Run:  uv run python -m evaluation.generation
      uv run python -m evaluation.generation --limit 6   # quick pass
"""

import argparse
import statistics as st

from core.config import settings
from evaluation.run import load_questions
from retrieval.answer import ask
from retrieval.retriever import DEFAULT_K


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--k", type=int, default=DEFAULT_K)
    parser.add_argument("--limit", type=int, default=None, help="first N questions per slice")
    args = parser.parse_args()

    questions = load_questions()
    if args.limit:
        by_slice: dict[str, list[dict]] = {}
        for q in questions:
            by_slice.setdefault(q["slice"], []).append(q)
        questions = [q for rows in by_slice.values() for q in rows[: args.limit]]

    model = settings.ollama_model if settings.llm_provider == "ollama" else settings.openai_model
    print(f"model: {model}   k={args.k}   {len(questions)} questions\n")

    rows = []
    for i, q in enumerate(questions, 1):
        answer = ask(q["question"], k=args.k)
        cited_ids = [s.paper_id for s in answer.sources]
        rows.append(
            {
                "slice": q["slice"],
                "expected": q["expected"],
                "refused": answer.refused,
                "cited_expected": bool(q["expected"]) and q["expected"] in cited_ids,
                "n_cited": len(answer.sources),
                "invalid": answer.invalid_citations,
                "latency": answer.latency_ms,
            }
        )
        mark = "REFUSED" if answer.refused else f"{len(answer.sources)} cited"
        print(f"  {i:>2}/{len(questions)}  [{q['slice'][:12]:<12}] {mark:<9} {q['question'][:46]}")

    print(f"\n{'=' * 70}")
    for name in ("in_corpus", "keyword", "out_of_corpus"):
        group = [r for r in rows if r["slice"] == name]
        if not group:
            continue
        refused = sum(r["refused"] for r in group)
        print(f"\n[{name}]  {len(group)} questions")
        if name == "out_of_corpus":
            print(f"  refused           {refused}/{len(group)}  ({refused / len(group):.0%})")
        else:
            scored = [r for r in group if r["expected"]]
            print(f"  answered          {len(group) - refused}/{len(group)}")
            if scored:
                hit = sum(r["cited_expected"] for r in scored)
                print(f"  cited expected    {hit}/{len(scored)}  ({hit / len(scored):.0%})")
            print(f"  mean sources used {st.mean(r['n_cited'] for r in group):.1f}")

    invalid = [r for r in rows if r["invalid"]]
    print(f"\n[citations]  invented source numbers: {len(invalid)}/{len(rows)}")
    if invalid:
        print(f"  {[r['invalid'] for r in invalid]}")

    latencies = [r["latency"] for r in rows]
    print(
        f"[latency]    median {st.median(latencies) / 1000:.1f}s"
        f"   max {max(latencies) / 1000:.1f}s"
    )


if __name__ == "__main__":
    main()
