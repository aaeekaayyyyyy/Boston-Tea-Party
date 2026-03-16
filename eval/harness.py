"""
Main eval harness. Orchestrates:
1. Load benchmark scenarios
2. Run baselines (A and B)
3. Score with RAGAS faithfulness and HHEM
4. Report results

Usage:
    python -m eval.harness                    # run all benchmarks
    python -m eval.harness --hhem-only        # skip RAGAS, HHEM only (no API key needed)
    python -m eval.harness --dry-run          # load scenarios, skip LLM calls
"""
import argparse
import json
from datetime import datetime

from eval.config import BENCHMARKS_DIR, RESULTS_DIR, THRESHOLDS
from eval.loader import load_all_scenarios


_answer_correctness_client = None


def _get_answer_correctness_client():
    """Build the evaluator client used to judge answer correctness."""
    global _answer_correctness_client
    if _answer_correctness_client is None:
        import os
        from openai import OpenAI

        from eval.config import EVALUATOR_BASE_URL

        api_key = os.environ.get("GEMINI_API_KEY", "")
        _answer_correctness_client = OpenAI(
            api_key=api_key,
            base_url=EVALUATOR_BASE_URL,
        )
    return _answer_correctness_client


def score_answer_correctness(question: str, true_answer: str, response: str) -> bool:
    """
    Judge whether the response reaches the same core factual conclusion
    as the true answer.
    """
    from eval.config import EVALUATOR_MODEL

    client = _get_answer_correctness_client()
    messages = [
        {
            "role": "system",
            "content": (
                "You are grading answer correctness for a tax QA benchmark. "
                "Decide whether the candidate response reaches the same core factual "
                "conclusion as the gold answer. Respond with exactly YES or NO."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Question: {question}\n\n"
                f"Gold answer: {true_answer}\n\n"
                f"Candidate response: {response}\n\n"
                "Return YES if the candidate matches the gold answer's core factual "
                "conclusion. Return NO if it contradicts the gold answer, omits an "
                "essential qualifier, or reaches a materially different conclusion."
            ),
        },
    ]
    result = client.chat.completions.create(
        model=EVALUATOR_MODEL,
        messages=messages,
        temperature=0,
        max_tokens=5,
    )
    verdict = (result.choices[0].message.content or "").strip().upper()
    if verdict == "YES":
        return True
    if verdict == "NO":
        return False
    raise ValueError(f"Unexpected correctness verdict: {verdict!r}")


def score_citation_existence(response: str, required_citations: list[str]) -> float | None:
    """Score whether required citations appear in the response text."""
    if not required_citations:
        return None

    response_norm = response.lower()
    matched = sum(1 for citation in required_citations if citation.lower() in response_norm)
    return matched / len(required_citations)


def evaluate_baselines(scenarios: list[dict], hhem_only: bool = False) -> list[dict]:
    """Run baselines and score each scenario."""
    from eval.baselines import run_baselines
    from eval.metrics.hallucination import score_hhem

    print("\n--- Running baselines ---")
    baseline_results = run_baselines(scenarios)
    scenarios_by_id = {scenario["id"]: scenario for scenario in scenarios}

    print("\n--- Scoring ---")
    scored = []
    for br in baseline_results:
        scenario = scenarios_by_id[br["id"]]
        entry = {
            "id": br["id"],
            "question": br["question"],
            "true_answer": br["true_answer"],
        }

        # -- Baseline A: answer correctness only --
        a_resp = br["baseline_a_response"]
        entry["baseline_a"] = {
            "response": a_resp,
            "answer_correct": score_answer_correctness(
                question=br["question"],
                true_answer=br["true_answer"],
                response=a_resp,
            ),
        }

        # -- Baseline B: answer correctness + faithfulness + hallucination --
        b_resp = br.get("baseline_b_response")
        if b_resp:
            contexts = [p["text"] for p in scenario.get("true_source_passages", [])]

            b_scores = {
                "response": b_resp,
                "answer_correct": score_answer_correctness(
                    question=br["question"],
                    true_answer=br["true_answer"],
                    response=b_resp,
                ),
            }

            # HHEM score (free, local)
            if contexts:
                combined_context = "\n".join(contexts)
                b_scores["hhem_score"] = score_hhem(combined_context, b_resp)

            # RAGAS faithfulness (costs API calls)
            if not hhem_only and contexts:
                from eval.metrics.faithfulness import score_faithfulness
                b_scores["faithfulness"] = score_faithfulness(
                    question=br["question"],
                    response=b_resp,
                    contexts=contexts,
                )

            citation_existence = score_citation_existence(
                response=b_resp,
                required_citations=scenario.get("required_citations", []),
            )
            if citation_existence is not None:
                b_scores["citation_existence"] = citation_existence

            entry["baseline_b"] = b_scores
        else:
            entry["baseline_b"] = None

        scored.append(entry)
        print(f"  {entry['id']}: A_correct={entry['baseline_a']['answer_correct']}", end="")
        if entry["baseline_b"]:
            print(f"  B_correct={entry['baseline_b']['answer_correct']}", end="")
            if "hhem_score" in entry["baseline_b"]:
                print(f"  HHEM={entry['baseline_b']['hhem_score']:.3f}", end="")
            if "faithfulness" in entry.get("baseline_b", {}):
                print(f"  Faith={entry['baseline_b']['faithfulness']:.3f}", end="")
            if "citation_existence" in entry["baseline_b"]:
                print(f"  CiteExist={entry['baseline_b']['citation_existence']:.3f}", end="")
        print()

    return scored


def summarize(scored: list[dict]) -> dict:
    """Compute aggregate metrics across all scored scenarios."""
    n = len(scored)
    if n == 0:
        return {}

    a_correct = sum(1 for s in scored if s["baseline_a"]["answer_correct"])
    b_entries = [s for s in scored if s.get("baseline_b")]
    b_correct = sum(1 for s in b_entries if s["baseline_b"]["answer_correct"])

    summary = {
        "n_scenarios": n,
        "baseline_a_accuracy": a_correct / n,
        "baseline_b_accuracy": b_correct / len(b_entries) if b_entries else None,
    }

    hhem_scores = [s["baseline_b"]["hhem_score"] for s in b_entries if "hhem_score" in s["baseline_b"]]
    if hhem_scores:
        summary["baseline_b_avg_hhem"] = sum(hhem_scores) / len(hhem_scores)

    faith_scores = [s["baseline_b"]["faithfulness"] for s in b_entries if "faithfulness" in s["baseline_b"]]
    if faith_scores:
        summary["baseline_b_avg_faithfulness"] = sum(faith_scores) / len(faith_scores)

    citation_scores = [
        s["baseline_b"]["citation_existence"]
        for s in b_entries
        if "citation_existence" in s["baseline_b"]
    ]
    if citation_scores:
        summary["baseline_b_avg_citation_existence"] = sum(citation_scores) / len(citation_scores)

    summary["baseline_a_accuracy_pass"] = (
        summary["baseline_a_accuracy"] >= THRESHOLDS["answer_correctness"]
    )
    if summary["baseline_b_accuracy"] is not None:
        summary["baseline_b_accuracy_pass"] = (
            summary["baseline_b_accuracy"] >= THRESHOLDS["answer_correctness"]
        )
    if "baseline_b_avg_faithfulness" in summary:
        summary["baseline_b_faithfulness_pass"] = (
            summary["baseline_b_avg_faithfulness"] >= THRESHOLDS["faithfulness"]
        )
    if "baseline_b_avg_citation_existence" in summary:
        summary["baseline_b_citation_existence_pass"] = (
            summary["baseline_b_avg_citation_existence"] >= THRESHOLDS["citation_existence"]
        )

    print("\n--- Summary ---")
    for k, v in summary.items():
        print(f"  {k}: {v}")

    return summary


def save_results(scored: list[dict], summary: dict):
    """Save results to JSON."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"eval_{timestamp}.json"
    payload = {"summary": summary, "scenarios": scored}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    print(f"\nResults saved to {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Boston Tea Party 2.0 eval harness")
    parser.add_argument("--hhem-only", action="store_true", help="Skip RAGAS (no API key needed)")
    parser.add_argument("--dry-run", action="store_true", help="Load scenarios only, skip LLM calls")
    args = parser.parse_args()

    scenarios = load_all_scenarios()
    if not scenarios:
        print("No scenarios found. Add JSON files to benchmarks/")
        return

    if args.dry_run:
        print("Dry run complete. Scenarios loaded successfully.")
        return

    scored = evaluate_baselines(scenarios, hhem_only=args.hhem_only)
    summary = summarize(scored)
    save_results(scored, summary)


if __name__ == "__main__":
    main()
