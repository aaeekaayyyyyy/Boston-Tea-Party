"""
Main eval harness. Orchestrates:
1. Load benchmark scenarios
2. Run baselines (A and B)
3. Score with RAGAS faithfulness, LettuceDetect, citation existence, and citation F1
4. Report results with threshold pass/fail

Usage:
    python -m eval.harness                    # run all benchmarks
    python -m eval.harness --hhem-only        # legacy flag: skip faithfulness/API calls
    python -m eval.harness --dry-run          # load scenarios, skip LLM calls
"""
import argparse
import json
from datetime import datetime

from eval.config import RESULTS_DIR, THRESHOLDS
from eval.loader import load_all_scenarios
from eval.metrics.citation_utils import citation_in_text


_answer_correctness_client = None


def _get_answer_correctness_client():
    """Lazy-load the evaluator client used for answer-correctness grading."""
    global _answer_correctness_client
    if _answer_correctness_client is None:
        import os
        from openai import OpenAI
        from eval.config import EVALUATOR_BASE_URL
        api_key = os.environ.get("GEMINI_API_KEY", "")
        _answer_correctness_client = OpenAI(api_key=api_key, base_url=EVALUATOR_BASE_URL)
    return _answer_correctness_client


def score_answer_correctness(question: str, true_answer: str, response: str) -> bool:
    """Use the evaluator LLM to judge whether a response matches the gold answer."""
    from eval.config import EVALUATOR_MODEL
    client = _get_answer_correctness_client()
    messages = [
        {"role": "system", "content": "You are grading answer correctness for a tax QA benchmark. Decide whether the candidate response reaches the same core factual conclusion as the gold answer. Respond with exactly YES or NO."},
        {"role": "user", "content": f"Question: {question}\n\nGold answer: {true_answer}\n\nCandidate response: {response}\n\nReturn YES if the candidate matches the gold answer's core factual conclusion. Return NO if it contradicts the gold answer, omits an essential qualifier, or reaches a materially different conclusion."},
    ]
    result = client.chat.completions.create(model=EVALUATOR_MODEL, messages=messages, temperature=0, max_tokens=5)
    verdict = (result.choices[0].message.content or "").strip().upper()
    if verdict == "YES":
        return True
    if verdict == "NO":
        return False
    raise ValueError(f"Unexpected correctness verdict: {verdict!r}")


def score_citation_existence(response: str, required_citations: list[str]) -> float | None:
    """Score the fraction of required citations that appear in the response."""
    if not required_citations:
        return None
    matched = sum(1 for citation in required_citations if citation_in_text(response, citation))
    return matched / len(required_citations)


def evaluate_baselines(scenarios: list[dict], hhem_only: bool = False) -> list[dict]:
    """Run the baselines and attach all currently implemented eval metrics."""
    from eval.baselines import run_baselines

    print("\n--- Running baselines ---")
    baseline_results = run_baselines(scenarios)
    scenarios_by_id = {s["id"]: s for s in scenarios}

    print("\n--- Scoring ---")
    scored = []
    for br in baseline_results:
        scenario = scenarios_by_id[br["id"]]
        entry = {"id": br["id"], "question": br["question"], "true_answer": br["true_answer"]}

        a_resp = br["baseline_a_response"]
        entry["baseline_a"] = {
            "response": a_resp,
            "answer_correct": score_answer_correctness(br["question"], br["true_answer"], a_resp),
        }

        b_resp = br.get("baseline_b_response")
        if b_resp:
            contexts = [p["text"] for p in scenario.get("true_source_passages", [])]
            b_scores = {
                "response": b_resp,
                "answer_correct": score_answer_correctness(br["question"], br["true_answer"], b_resp),
            }

            # LettuceDetect span-level hallucination (metric #4)
            if contexts:
                try:
                    from eval.metrics.lettucedetect_metric import score_lettucedetect
                    ld = score_lettucedetect(contexts=contexts, question=br["question"], answer=b_resp)
                    b_scores["hallucination_rate"] = ld["hallucination_rate"]
                    b_scores["hallucinated_spans"] = ld["hallucinated_spans"]
                except Exception as e:
                    b_scores["hallucination_rate"] = 1.0
                    b_scores["hallucinated_spans"] = []
                    b_scores["hallucination_error"] = str(e)
                    print(f"    LettuceDetect failed for {br['id']}: {e}")

            # RAGAS faithfulness (metric #3, costs API calls)
            if not hhem_only and contexts:
                from eval.metrics.faithfulness import score_faithfulness
                b_scores["faithfulness"] = score_faithfulness(
                    question=br["question"], response=b_resp, contexts=contexts,
                )

            # Citation existence (metric #5)
            cite_exist = score_citation_existence(b_resp, scenario.get("required_citations", []))
            if cite_exist is not None:
                b_scores["citation_existence"] = cite_exist

            # Citation F1 via NLI (metric #6)
            required_cites = scenario.get("required_citations", [])
            true_passages = scenario.get("true_source_passages", [])
            if required_cites and true_passages:
                try:
                    from eval.metrics.citation_nli import score_citation_f1
                    cf1 = score_citation_f1(
                        response=b_resp,
                        required_citations=required_cites,
                        true_source_passages=true_passages,
                    )
                    b_scores["citation_recall"] = cf1["citation_recall"]
                    b_scores["citation_precision"] = cf1["citation_precision"]
                    b_scores["citation_f1"] = cf1["citation_f1"]
                    b_scores["citation_nli_details"] = cf1["details"]
                except Exception as e:
                    b_scores["citation_recall"] = 0.0
                    b_scores["citation_precision"] = 0.0
                    b_scores["citation_f1"] = 0.0
                    b_scores["citation_nli_details"] = []
                    b_scores["citation_nli_error"] = str(e)
                    print(f"    Citation F1 failed for {br['id']}: {e}")

            entry["baseline_b"] = b_scores
        else:
            entry["baseline_b"] = None

        scored.append(entry)

        # console output
        print(f"  {entry['id']}: A_correct={entry['baseline_a']['answer_correct']}", end="")
        if entry["baseline_b"]:
            b = entry["baseline_b"]
            print(f"  B_correct={b['answer_correct']}", end="")
            if "hallucination_rate" in b:
                print(f"  HalRate={b['hallucination_rate']:.3f}", end="")
            if "faithfulness" in b:
                print(f"  Faith={b['faithfulness']:.3f}", end="")
            if "citation_existence" in b:
                print(f"  CiteExist={b['citation_existence']:.3f}", end="")
            if "citation_f1" in b:
                print(f"  CitF1={b['citation_f1']:.3f}", end="")
        print()

    return scored


def summarize(scored: list[dict]) -> dict:
    """Aggregate per-scenario results into summary metrics and threshold checks."""
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

    hal = [s["baseline_b"]["hallucination_rate"] for s in b_entries if "hallucination_rate" in s["baseline_b"]]
    if hal:
        summary["baseline_b_avg_hallucination_rate"] = sum(hal) / len(hal)

    faith = [s["baseline_b"]["faithfulness"] for s in b_entries if "faithfulness" in s["baseline_b"]]
    if faith:
        summary["baseline_b_avg_faithfulness"] = sum(faith) / len(faith)

    cite_exist = [s["baseline_b"]["citation_existence"] for s in b_entries if "citation_existence" in s["baseline_b"]]
    if cite_exist:
        summary["baseline_b_avg_citation_existence"] = sum(cite_exist) / len(cite_exist)

    cite_f1 = [s["baseline_b"]["citation_f1"] for s in b_entries if "citation_f1" in s["baseline_b"]]
    if cite_f1:
        summary["baseline_b_avg_citation_f1"] = sum(cite_f1) / len(cite_f1)
    cite_recall = [s["baseline_b"]["citation_recall"] for s in b_entries if "citation_recall" in s["baseline_b"]]
    if cite_recall:
        summary["baseline_b_avg_citation_recall"] = sum(cite_recall) / len(cite_recall)
    cite_prec = [s["baseline_b"]["citation_precision"] for s in b_entries if "citation_precision" in s["baseline_b"]]
    if cite_prec:
        summary["baseline_b_avg_citation_precision"] = sum(cite_prec) / len(cite_prec)

    # threshold checks
    summary["baseline_a_accuracy_pass"] = summary["baseline_a_accuracy"] >= THRESHOLDS["answer_correctness"]
    if summary["baseline_b_accuracy"] is not None:
        summary["baseline_b_accuracy_pass"] = summary["baseline_b_accuracy"] >= THRESHOLDS["answer_correctness"]
    if "baseline_b_avg_faithfulness" in summary:
        summary["baseline_b_faithfulness_pass"] = summary["baseline_b_avg_faithfulness"] >= THRESHOLDS["faithfulness"]
    if "baseline_b_avg_citation_existence" in summary:
        summary["baseline_b_citation_existence_pass"] = summary["baseline_b_avg_citation_existence"] >= THRESHOLDS["citation_existence"]
    if "baseline_b_avg_hallucination_rate" in summary:
        summary["baseline_b_hallucination_rate_pass"] = summary["baseline_b_avg_hallucination_rate"] <= THRESHOLDS["hallucination_rate"]

    print("\n--- Summary ---")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    return summary


def save_results(scored: list[dict], summary: dict):
    """Persist the scored scenarios and summary to eval/results/."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"eval_{timestamp}.json"
    payload = {"summary": summary, "scenarios": scored}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    print(f"\nResults saved to {out_path}")


def main():
    """Run the eval harness CLI."""
    parser = argparse.ArgumentParser(description="Boston Tea Party 2.0 eval harness")
    parser.add_argument(
        "--hhem-only",
        action="store_true",
        help="Legacy compatibility flag: skip faithfulness/API calls and run local-only metrics",
    )
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
