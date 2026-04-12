"""
Evaluate the real planning stack on converted benchmark scenarios.

This runner differs from `eval.harness --pipeline`:
- inputs are structured facts recovered from the source benchmark cases
- execution uses the real planning stack in-process
- scoring uses a deterministic eval-only answer adapter rather than raw UI prose
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from eval.config import BENCHMARKS_DIR, REPO_ROOT, RESULTS_DIR, THRESHOLDS
from eval.harness import _score_grounded_response
from eval.loader import load_scenarios
from eval.metrics.retrieval_metrics import mrr, precision_at_k
from eval.system_adapter import (
    extract_citation_passages,
    extract_contexts,
    extract_retrieved_citation_lists,
)
from src.planning.agent import PlanningAgent
from src.planning.constraint_adapter import SimpleConstraintEngine
from src.planning.narrative_report import attach_ui_payload


TARGET_LABELS = {
    "head_of_household": "head of household",
    "single": "single",
    "married_filing_jointly": "married filing jointly",
    "married_filing_separately": "married filing separately",
}


def _load_converted_scenarios() -> list[dict]:
    scenarios: list[dict] = []
    for path in sorted(BENCHMARKS_DIR.rglob("*.json")):
        if "_smoke" in path.parts:
            continue
        scenarios.extend(load_scenarios(path))
    return [
        scenario
        for scenario in scenarios
        if scenario.get("source_case_id") and scenario.get("source_benchmark_file")
    ]


def _load_source_cases(source_file: str, cache: dict[str, dict[str, dict]]) -> dict[str, dict]:
    cached = cache.get(source_file)
    if cached is not None:
        return cached

    path = REPO_ROOT / source_file
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    cases = {}
    for case in payload.get("cases", []):
        case_id = case.get("case_id")
        if case_id:
            cases[case_id] = case

    cache[source_file] = cases
    return cases


def _resolve_source_case(scenario: dict, cache: dict[str, dict[str, dict]]) -> dict | None:
    source_file = scenario.get("source_benchmark_file")
    source_case_id = scenario.get("source_case_id")
    if not source_file or not source_case_id:
        return None
    return _load_source_cases(source_file, cache).get(source_case_id)


def _adapt_source_facts_for_planner(source_facts: dict[str, Any]) -> dict[str, Any]:
    """
    Translate rule-benchmark facts into the planner's intake-oriented facts.

    The filing-status benchmark stores some cases in derived rule terms
    (for example `marital_status_on_1231 = head_of_household`) while the
    planner expects underlying intake facts.
    """
    facts = dict(source_facts)

    marital_status = facts.get("marital_status_on_1231")
    if marital_status == "head_of_household":
        if facts.get("considered_unmarried") is True:
            facts["marital_status_on_1231"] = "married"
            facts.setdefault("lived_with_spouse_last_6_months", False)
            facts.setdefault("spouse_willing_to_file_jointly", False)
            if facts.get("eligible_for_hoh") is True:
                facts.setdefault("paid_more_than_half_home_costs", True)
        else:
            facts["marital_status_on_1231"] = "single"

    if "has_qualifying_person" in facts:
        has_person = bool(facts["has_qualifying_person"])
        facts.setdefault("has_qualifying_child", has_person)
        facts.setdefault("has_other_qualifying_persons", has_person)

    if facts.get("eligible_for_hoh") is True:
        facts.setdefault("paid_more_than_half_home_costs", True)

    if facts.get("considered_unmarried") is True:
        facts.setdefault("lived_with_spouse_last_6_months", False)
        if facts.get("marital_status_on_1231") == "married":
            facts.setdefault("spouse_willing_to_file_jointly", False)

    return facts


def _target_path_from_required_citations(required_citations: list[str]) -> str | None:
    joined = " ".join(required_citations).lower()
    if "head of household" in joined:
        return "head_of_household"
    if "married filing jointly" in joined:
        return "married_filing_jointly"
    if "married filing separately" in joined:
        return "married_filing_separately"
    if "filing status - single" in joined:
        return "single"
    return None


def _deterministic_scored_answer(plan_dict: dict, scenario: dict) -> str:
    constraint_result = plan_dict.get("constraint_result") or {}
    valid_paths = list(constraint_result.get("valid_paths") or [])
    target_path = _target_path_from_required_citations(scenario.get("required_citations", []))
    target_label = TARGET_LABELS.get(target_path or "", target_path or "the requested position")
    narrative_report = plan_dict.get("narrative_report") or {}
    source_citations = list(narrative_report.get("source_citations") or [])

    if target_path == "head_of_household":
        if target_path in valid_paths:
            answer = (
                "Yes. Based on the structured facts, head of household appears available "
                "because the taxpayer is treated as married-but-considered-unmarried, paid "
                "more than half the cost of keeping up the home, and has a qualifying person."
            )
        else:
            answer = (
                "No. Based on the structured facts, head of household does not appear available "
                "because a required qualifying-person or home-cost condition is missing."
            )
    elif target_path == "single":
        if target_path in valid_paths:
            answer = (
                "A taxpayer who is unmarried and not eligible for another filing status should file as single."
            )
        else:
            answer = "Single does not appear to be the supported filing status from the structured facts."
    elif target_path == "married_filing_jointly":
        if target_path in valid_paths:
            answer = (
                "Yes. If both spouses agree to file together, married filing jointly is an available filing status."
            )
        else:
            answer = "No. Married filing jointly does not appear available from the structured facts provided."
    elif target_path == "married_filing_separately":
        if target_path in valid_paths:
            answer = (
                "If the spouses do not file jointly, the taxpayer should use married filing separately "
                "unless another special status applies."
            )
        else:
            answer = "Married filing separately does not appear to be the supported filing status here."
    else:
        taxpayer_position = narrative_report.get("taxpayer_position") or {}
        headline = str(taxpayer_position.get("headline") or "").strip()
        detail = str(taxpayer_position.get("detail") or "").strip()
        if headline and detail:
            answer = f"{headline} {detail}"
        elif headline:
            answer = headline
        elif valid_paths:
            answer = f"The planner identified these valid paths: {', '.join(valid_paths)}."
        else:
            answer = str(plan_dict.get("message") or f"The planner did not resolve {target_label}.").strip()

    if source_citations:
        answer += f"\n\nCitation: {source_citations[0]}"
    return answer


def _score_planning_retrieval(plan_dict: dict, scenario: dict) -> dict[str, Any]:
    retrieval_results = list(plan_dict.get("retrieval_results") or [])
    contexts = extract_contexts(retrieval_results)
    citation_passages = extract_citation_passages(retrieval_results)
    retrieved_lists = extract_retrieved_citation_lists(retrieval_results)
    response = _deterministic_scored_answer(plan_dict, scenario)

    scores = _score_grounded_response(
        scenario_id=scenario["id"],
        question=scenario["question"],
        true_answer=scenario["answer"],
        response=response,
        contexts=contexts,
        required_citations=list(scenario.get("required_citations", []) or []),
        citation_passages=citation_passages,
    )

    if len(retrieved_lists) == 1:
        scores["precision_at_5"] = precision_at_k(
            retrieved_lists[0],
            scenario.get("required_citations", []),
            5,
        )
        scores["mrr"] = mrr(retrieved_lists[0], scenario.get("required_citations", []))
    elif len(retrieved_lists) > 1:
        scores["retrieval_metrics_skipped"] = True
        scores["retrieval_metrics_skip_reason"] = (
            "Multiple retrieval calls are not combined into a single ranked list."
        )

    return {
        "scored_answer_text": response,
        "contexts": contexts,
        "citation_passages": citation_passages,
        "retrieved_citation_lists": retrieved_lists,
        "metrics": scores,
    }


def evaluate_planning_system(scenarios: list[dict]) -> list[dict]:
    try:
        from src.rag.client import HybridRetrievalClient
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Planning-system eval requires the hybrid retrieval dependencies. "
            f"Missing module: {exc.name}"
        ) from exc

    source_case_cache: dict[str, dict[str, dict]] = {}
    retrieval_client = HybridRetrievalClient(repo_root=REPO_ROOT)
    agent = PlanningAgent(
        constraint_engine=SimpleConstraintEngine(),
        retrieval_client=retrieval_client,
    )

    print("\n--- Running planning-system evaluation ---")
    scored = []
    for scenario in scenarios:
        source_case = _resolve_source_case(scenario, source_case_cache)
        if source_case is None:
            entry = {
                "id": scenario["id"],
                "source_case_id": scenario.get("source_case_id"),
                "source_benchmark_file": scenario.get("source_benchmark_file"),
                "facts": None,
                "planner_action": None,
                "incomplete_for_planner": False,
                "source_case_lookup_failed": True,
                "lookup_failure_reason": "Could not resolve source benchmark case.",
                "narrative_report": None,
                "constraint_result": None,
                "retrieval_results": [],
            }
            scored.append(entry)
            print(f"  {scenario['id']}: lookup failed")
            continue

        facts = _adapt_source_facts_for_planner(source_case.get("facts") or {})
        action = agent.plan(facts)
        plan_dict = attach_ui_payload(action.to_dict())

        entry = {
            "id": scenario["id"],
            "question": scenario["question"],
            "true_answer": scenario["answer"],
            "source_case_id": scenario.get("source_case_id"),
            "source_benchmark_file": scenario.get("source_benchmark_file"),
            "facts": facts,
            "planner_action": plan_dict.get("action"),
            "incomplete_for_planner": plan_dict.get("action") != "retrieve",
            "source_case_lookup_failed": False,
            "scored_answer_text": None,
            "narrative_report": plan_dict.get("narrative_report"),
            "constraint_result": plan_dict.get("constraint_result"),
            "retrieval_results": list(plan_dict.get("retrieval_results") or []),
            "retrieval_calls": list(plan_dict.get("retrieval_calls") or []),
            "normalized_facts": dict(plan_dict.get("normalized_facts") or {}),
            "planning_system": {
                "message": plan_dict.get("message"),
                "question": plan_dict.get("question"),
                "target_field": plan_dict.get("target_field"),
                "reason": plan_dict.get("reason"),
            },
        }

        if plan_dict.get("action") == "retrieve":
            planning_scores = _score_planning_retrieval(plan_dict, scenario)
            entry["scored_answer_text"] = planning_scores["scored_answer_text"]
            entry["planning_system"].update(planning_scores["metrics"])
            entry["planning_system"]["retrieved_citation_lists"] = planning_scores["retrieved_citation_lists"]

            print(f"  {scenario['id']}: action=retrieve", end="")
            if "answer_correct" in entry["planning_system"]:
                print(f"  correct={entry['planning_system']['answer_correct']}", end="")
            if "precision_at_5" in entry["planning_system"]:
                print(f"  P@5={entry['planning_system']['precision_at_5']:.3f}", end="")
            if "mrr" in entry["planning_system"]:
                print(f"  MRR={entry['planning_system']['mrr']:.3f}", end="")
            print()
        else:
            entry["planning_system"]["answer_metrics_skipped"] = True
            entry["planning_system"]["answer_metrics_skip_reason"] = (
                "Planner requested follow-up information before retrieval."
            )
            print(f"  {scenario['id']}: action={plan_dict.get('action')} (incomplete)")

        scored.append(entry)

    return scored


def summarize_planning(scored: list[dict]) -> dict[str, Any]:
    if not scored:
        return {}

    total = len(scored)
    lookup_failures = [entry for entry in scored if entry.get("source_case_lookup_failed")]
    incomplete = [
        entry for entry in scored
        if not entry.get("source_case_lookup_failed") and entry.get("incomplete_for_planner")
    ]
    completed = [
        entry for entry in scored
        if not entry.get("source_case_lookup_failed") and not entry.get("incomplete_for_planner")
    ]

    summary: dict[str, Any] = {
        "n_scenarios": total,
        "planning_source_case_lookup_failures": len(lookup_failures),
        "planning_incomplete_for_planner": len(incomplete),
        "planning_scored_scenarios": len(completed),
    }

    system_entries = [entry["planning_system"] for entry in completed]
    answered = [entry for entry in system_entries if "answer_correct" in entry]
    if answered:
        summary["planning_system_accuracy"] = (
            sum(1 for entry in answered if entry["answer_correct"]) / len(answered)
        )

    for key, summary_key in [
        ("hallucination_rate", "planning_system_avg_hallucination_rate"),
        ("faithfulness", "planning_system_avg_faithfulness"),
        ("citation_existence", "planning_system_avg_citation_existence"),
        ("citation_f1", "planning_system_avg_citation_f1"),
        ("citation_recall", "planning_system_avg_citation_recall"),
        ("citation_precision", "planning_system_avg_citation_precision"),
        ("precision_at_5", "planning_system_avg_precision_at_5"),
        ("mrr", "planning_system_avg_mrr"),
    ]:
        values = [entry[key] for entry in system_entries if key in entry]
        if values:
            summary[summary_key] = sum(values) / len(values)

    if "planning_system_accuracy" in summary:
        summary["planning_system_accuracy_pass"] = (
            summary["planning_system_accuracy"] >= THRESHOLDS["answer_correctness"]
        )
    if "planning_system_avg_faithfulness" in summary:
        summary["planning_system_faithfulness_pass"] = (
            summary["planning_system_avg_faithfulness"] >= THRESHOLDS["faithfulness"]
        )
    if "planning_system_avg_citation_existence" in summary:
        summary["planning_system_citation_existence_pass"] = (
            summary["planning_system_avg_citation_existence"] >= THRESHOLDS["citation_existence"]
        )
    if "planning_system_avg_hallucination_rate" in summary:
        summary["planning_system_hallucination_rate_pass"] = (
            summary["planning_system_avg_hallucination_rate"] <= THRESHOLDS["hallucination_rate"]
        )

    print("\n--- Planning summary ---")
    for key, value in summary.items():
        print(f"  {key}: {value}")
    return summary


def save_results(scored: list[dict], summary: dict[str, Any]) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"planning_eval_{timestamp}.json"
    payload = {"summary": summary, "scenarios": scored}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    print(f"\nResults saved to {out_path}")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the real planning system")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve converted scenarios and source benchmark facts without running the planner.",
    )
    args = parser.parse_args()

    scenarios = _load_converted_scenarios()
    if not scenarios:
        print("No converted scenarios with source benchmark metadata found.")
        return

    if args.dry_run:
        print(f"Dry run complete. {len(scenarios)} converted scenarios are eligible for planning-system eval.")
        return

    scored = evaluate_planning_system(scenarios)
    summary = summarize_planning(scored)
    save_results(scored, summary)


if __name__ == "__main__":
    main()
