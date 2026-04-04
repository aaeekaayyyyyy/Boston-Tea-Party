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
    python -m eval.harness --system-results outputs.json
                                           # score precomputed system outputs
"""
import argparse
import json
from datetime import datetime
from pathlib import Path

from eval.config import RESULTS_DIR, THRESHOLDS
from eval.loader import load_all_scenarios
from eval.metrics.citation_utils import citation_in_text
from eval.metrics.retrieval_metrics import mrr, precision_at_k
from eval.system_adapter import adapt_system_output


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


def _score_grounded_response(
    *,
    scenario_id: str,
    question: str,
    true_answer: str,
    response: str,
    contexts: list[str],
    required_citations: list[str],
    citation_passages: list[dict],
    hhem_only: bool = False,
) -> dict:
    """Score a single grounded response using the existing answer-based metrics."""
    scores = {
        "response": response,
        "answer_correct": score_answer_correctness(question, true_answer, response),
    }

    if contexts:
        try:
            from eval.metrics.lettucedetect_metric import score_lettucedetect

            ld = score_lettucedetect(contexts=contexts, question=question, answer=response)
            scores["hallucination_rate"] = ld["hallucination_rate"]
            scores["hallucinated_spans"] = ld["hallucinated_spans"]
        except Exception as e:
            scores["hallucination_rate"] = 1.0
            scores["hallucinated_spans"] = []
            scores["hallucination_error"] = str(e)
            print(f"    LettuceDetect failed for {scenario_id}: {e}")

    if not hhem_only and contexts:
        from eval.metrics.faithfulness import score_faithfulness

        scores["faithfulness"] = score_faithfulness(
            question=question,
            response=response,
            contexts=contexts,
        )

    cite_exist = score_citation_existence(response, required_citations)
    if cite_exist is not None:
        scores["citation_existence"] = cite_exist

    if required_citations and citation_passages:
        try:
            from eval.metrics.citation_nli import score_citation_f1

            cf1 = score_citation_f1(
                response=response,
                required_citations=required_citations,
                true_source_passages=citation_passages,
            )
            scores["citation_recall"] = cf1["citation_recall"]
            scores["citation_precision"] = cf1["citation_precision"]
            scores["citation_f1"] = cf1["citation_f1"]
            scores["citation_nli_details"] = cf1["details"]
        except Exception as e:
            scores["citation_recall"] = 0.0
            scores["citation_precision"] = 0.0
            scores["citation_f1"] = 0.0
            scores["citation_nli_details"] = []
            scores["citation_nli_error"] = str(e)
            print(f"    Citation F1 failed for {scenario_id}: {e}")

    return scores


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
            b_scores = _score_grounded_response(
                scenario_id=br["id"],
                question=br["question"],
                true_answer=br["true_answer"],
                response=b_resp,
                contexts=contexts,
                required_citations=scenario.get("required_citations", []),
                citation_passages=scenario.get("true_source_passages", []),
                hhem_only=hhem_only,
            )
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


def load_system_results(path: Path) -> list[dict]:
    """Load a JSON array of precomputed system outputs."""
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    if not isinstance(payload, list):
        raise ValueError(f"Expected a JSON array in {path}, got {type(payload).__name__}")

    for i, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"Expected object at index {i} in {path}, got {type(item).__name__}")
        if "id" not in item:
            raise ValueError(f"Missing 'id' for system result at index {i} in {path}")
        if "system_output" not in item:
            raise ValueError(f"Missing 'system_output' for system result id={item.get('id')!r} in {path}")
    return payload


def evaluate_system_results(
    scenarios: list[dict],
    system_results: list[dict],
    hhem_only: bool = False,
) -> list[dict]:
    """Score precomputed system outputs using the metrics valid for current system mode."""
    scenarios_by_id = {scenario["id"]: scenario for scenario in scenarios}
    results_by_id = {result["id"]: result for result in system_results}

    missing = [scenario_id for scenario_id in scenarios_by_id if scenario_id not in results_by_id]
    if missing:
        print(f"\n--- System mode ---")
        print(f"Missing system outputs for {len(missing)} scenarios; they will be skipped.")

    unused = [result_id for result_id in results_by_id if result_id not in scenarios_by_id]
    if unused:
        print(f"Found {len(unused)} system outputs with no matching benchmark scenario; they will be ignored.")

    print("\n--- Scoring system results ---")
    scored = []
    for scenario in scenarios:
        system_result = results_by_id.get(scenario["id"])
        if not system_result:
            continue

        adapted = adapt_system_output(system_result, scenario)
        entry = {
            "id": scenario["id"],
            "question": scenario["question"],
            "true_answer": scenario["answer"],
            "system": {
                "response": adapted["response"],
                "constraint_output": adapted["constraint_output"],
                "gold_constraint": adapted["gold_constraint"],
                "strategy_metadata": adapted["strategy_metadata"],
                "retrieved_citation_lists": adapted["retrieved_citation_lists"],
            },
        }

        system_scores = entry["system"]
        response = adapted["response"]
        if response:
            system_scores.update(
                _score_grounded_response(
                    scenario_id=scenario["id"],
                    question=scenario["question"],
                    true_answer=scenario["answer"],
                    response=response,
                    contexts=adapted["contexts"],
                    required_citations=adapted["required_citations"],
                    citation_passages=adapted["citation_passages"],
                    hhem_only=hhem_only,
                )
            )
        else:
            system_scores["answer_metrics_skipped"] = True
            system_scores["answer_metrics_skip_reason"] = "No response text provided in system results."

        retrieved_lists = adapted["retrieved_citation_lists"]
        if len(retrieved_lists) == 1:
            system_scores["precision_at_5"] = precision_at_k(
                retrieved_lists[0],
                adapted["required_citations"],
                5,
            )
            system_scores["mrr"] = mrr(retrieved_lists[0], adapted["required_citations"])
        elif len(retrieved_lists) > 1:
            system_scores["retrieval_metrics_skipped"] = True
            system_scores["retrieval_metrics_skip_reason"] = (
                "Multiple retrieval calls are not combined into a single ranked list."
            )

        scored.append(entry)

        print(f"  {entry['id']}:", end="")
        if "answer_correct" in system_scores:
            print(f" Sys_correct={system_scores['answer_correct']}", end="")
        else:
            print(" Sys_correct=SKIP", end="")
        if "precision_at_5" in system_scores:
            print(f"  P@5={system_scores['precision_at_5']:.3f}", end="")
        if "mrr" in system_scores:
            print(f"  MRR={system_scores['mrr']:.3f}", end="")
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


def summarize_system(scored: list[dict]) -> dict:
    """Aggregate system-mode scenario results into summary metrics."""
    n = len(scored)
    if n == 0:
        return {}

    system_entries = [entry["system"] for entry in scored]
    answered = [entry for entry in system_entries if "answer_correct" in entry]
    summary = {
        "n_scenarios": n,
        "system_accuracy": (
            sum(1 for entry in answered if entry["answer_correct"]) / len(answered)
            if answered else None
        ),
    }

    for key, summary_key in [
        ("hallucination_rate", "system_avg_hallucination_rate"),
        ("faithfulness", "system_avg_faithfulness"),
        ("citation_existence", "system_avg_citation_existence"),
        ("citation_f1", "system_avg_citation_f1"),
        ("citation_recall", "system_avg_citation_recall"),
        ("citation_precision", "system_avg_citation_precision"),
        ("precision_at_5", "system_avg_precision_at_5"),
        ("mrr", "system_avg_mrr"),
    ]:
        values = [entry[key] for entry in system_entries if key in entry]
        if values:
            summary[summary_key] = sum(values) / len(values)

    if summary["system_accuracy"] is not None:
        summary["system_accuracy_pass"] = summary["system_accuracy"] >= THRESHOLDS["answer_correctness"]
    if "system_avg_faithfulness" in summary:
        summary["system_faithfulness_pass"] = summary["system_avg_faithfulness"] >= THRESHOLDS["faithfulness"]
    if "system_avg_citation_existence" in summary:
        summary["system_citation_existence_pass"] = summary["system_avg_citation_existence"] >= THRESHOLDS["citation_existence"]
    if "system_avg_hallucination_rate" in summary:
        summary["system_hallucination_rate_pass"] = summary["system_avg_hallucination_rate"] <= THRESHOLDS["hallucination_rate"]

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
    parser.add_argument(
        "--system-results",
        type=Path,
        help="Path to a JSON array of precomputed system outputs",
    )
    args = parser.parse_args()

    all_scenarios = load_all_scenarios()
    if not all_scenarios:
        print("No scenarios found. Add JSON files to benchmarks/")
        return

    if args.system_results:
        system_results = load_system_results(args.system_results)
        print(f"Loaded {len(system_results)} precomputed system results from {args.system_results.name}")
        if args.dry_run:
            print("Dry run complete. Scenarios and system results loaded successfully.")
            return

        scored = evaluate_system_results(all_scenarios, system_results, hhem_only=args.hhem_only)
        summary = summarize_system(scored)
        save_results(scored, summary)
        return

    # Filter to question types the baseline scoring path supports.
    # Planning scenarios test agent behavior, not answer quality.
    BASELINE_QUESTION_TYPES = {"factual_lookup", "eligibility_determination", "calculation", None}
    scenarios = [
        s for s in all_scenarios
        if s.get("question_type") in BASELINE_QUESTION_TYPES
    ]
    skipped = len(all_scenarios) - len(scenarios)
    if skipped:
        print(f"Filtered to {len(scenarios)} baseline-scorable scenarios (skipped {skipped} planning/other)")

    if args.dry_run:
        print("Dry run complete. Scenarios loaded successfully.")
        return

    scored = evaluate_baselines(scenarios, hhem_only=args.hhem_only)
    summary = summarize(scored)
    save_results(scored, summary)


if __name__ == "__main__":
    main()
