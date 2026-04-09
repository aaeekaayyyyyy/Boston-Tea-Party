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
from eval.metrics.citation_utils import citation_in_text, source_citation_in_text
from eval.metrics.retrieval_metrics import (
    mrr, precision_at_k, source_mrr, source_precision_at_k,
)
from eval.system_adapter import adapt_system_output


_answer_correctness_client = None
_LETTUCEDETECT_MAX_TOKENS = 8192


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


def _estimate_lettucedetect_tokens(contexts: list[str], question: str, answer: str) -> int:
    """Conservative token estimate used to avoid overlength LettuceDetect calls."""
    text = "\n".join((contexts or []) + [question, answer])
    word_estimate = len(text.split())
    char_estimate = (len(text) + 3) // 4
    return max(word_estimate, char_estimate)


def _truncate_lettucedetect_contexts(
    contexts: list[str],
    question: str,
    answer: str,
    max_tokens: int = _LETTUCEDETECT_MAX_TOKENS,
) -> tuple[list[str], int]:
    """Keep full question+answer and trim contexts in order to fit the token budget."""
    kept = []
    for context in contexts or []:
        candidate = kept + [context]
        if _estimate_lettucedetect_tokens(candidate, question, answer) > max_tokens:
            break
        kept.append(context)
    return kept, _estimate_lettucedetect_tokens(kept, question, answer)


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
    """Strict section-level: fraction of required citations found in response."""
    if not required_citations:
        return None
    matched = sum(1 for citation in required_citations if citation_in_text(response, citation))
    return matched / len(required_citations)


def score_source_citation_existence(response: str, required_citations: list[str]) -> float | None:
    """Loose source-level: fraction of required source IDs found in response.
    Reported separately from section-level to avoid inflating precision."""
    if not required_citations:
        return None
    matched = sum(1 for citation in required_citations if source_citation_in_text(response, citation))
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
    enable_citation_f1: bool = True,
    citation_f1_skip_reason: str | None = None,
) -> dict:
    """Score a single grounded response using the existing answer-based metrics."""
    scores = {
        "response": response,
        "answer_correct": score_answer_correctness(question, true_answer, response),
    }

    if contexts:
        try:
            token_estimate = _estimate_lettucedetect_tokens(contexts, question, response)
            scoring_contexts = contexts
            if token_estimate > _LETTUCEDETECT_MAX_TOKENS:
                scoring_contexts, truncated_estimate = _truncate_lettucedetect_contexts(
                    contexts,
                    question,
                    response,
                )
                if not scoring_contexts:
                    scores["hallucination_skipped"] = True
                    scores["hallucination_skip_reason"] = (
                        "Input exceeds LettuceDetect context window, and no context passages fit after truncation."
                    )
                    scores["hallucination_estimated_tokens"] = token_estimate
                else:
                    from eval.metrics.lettucedetect_metric import score_lettucedetect

                    ld = score_lettucedetect(
                        contexts=scoring_contexts,
                        question=question,
                        answer=response,
                    )
                    scores["hallucination_rate"] = ld["hallucination_rate"]
                    scores["hallucinated_spans"] = ld["hallucinated_spans"]
                    scores["hallucination_truncated"] = True
                    scores["hallucination_original_context_count"] = len(contexts)
                    scores["hallucination_truncated_context_count"] = len(scoring_contexts)
                    scores["hallucination_estimated_tokens"] = token_estimate
                    scores["hallucination_truncated_estimated_tokens"] = truncated_estimate
                    scores["hallucination_truncation_reason"] = (
                        "Input exceeded LettuceDetect context window; scored on truncated context."
                    )
            else:
                from eval.metrics.lettucedetect_metric import score_lettucedetect

                ld = score_lettucedetect(contexts=scoring_contexts, question=question, answer=response)
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

    source_cite_exist = score_source_citation_existence(response, required_citations)
    if source_cite_exist is not None:
        scores["source_citation_existence"] = source_cite_exist

    if not enable_citation_f1:
        scores["citation_metrics_skipped"] = True
        scores["citation_metrics_skip_reason"] = (
            citation_f1_skip_reason
            or "Retrieved citations are not yet mapped to benchmark citation targets."
        )
    elif required_citations and citation_passages:
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
                "citation_mapping_applied": adapted["citation_mapping_applied"],
                "citation_mapping_details": adapted["citation_mapping_details"],
                "unmapped_required_citations": adapted["unmapped_required_citations"],
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
                    citation_passages=adapted["mapped_citation_passages"],
                    hhem_only=hhem_only,
                    enable_citation_f1=adapted["citation_mapping_applied"],
                    citation_f1_skip_reason=(
                        "No retrieved citations could be mapped to benchmark citation targets."
                    ),
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
            # Source-level (loose) retrieval metrics, reported separately
            system_scores["source_precision_at_5"] = source_precision_at_k(
                retrieved_lists[0],
                adapted["required_citations"],
                5,
            )
            system_scores["source_mrr"] = source_mrr(retrieved_lists[0], adapted["required_citations"])
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
        ("source_citation_existence", "system_avg_source_citation_existence"),
        ("citation_f1", "system_avg_citation_f1"),
        ("citation_recall", "system_avg_citation_recall"),
        ("citation_precision", "system_avg_citation_precision"),
        ("precision_at_5", "system_avg_precision_at_5"),
        ("mrr", "system_avg_mrr"),
        ("source_precision_at_5", "system_avg_source_precision_at_5"),
        ("source_mrr", "system_avg_source_mrr"),
    ]:
        values = [entry[key] for entry in system_entries if key in entry]
        if values:
            summary[summary_key] = sum(values) / len(values)

    summary["system_hallucination_truncated_cases"] = sum(
        1 for entry in system_entries if entry.get("hallucination_truncated")
    )

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



# -- Pipeline mode: retrieve + generate + score in one pass --------------------


def _pick_source_hint(scenario: dict) -> str | None:
    """Infer source_hint from the scenario's source_type field."""
    st = scenario.get("source_type", "")
    if st == "irc":
        return "irc"
    if st in ("irs_pubs", "irs_pub"):
        return "irs_pubs"
    if st == "tax_court":
        return "tax_court"
    return None


def run_pipeline(scenarios: list[dict], top_k: int = 5) -> list[dict]:
    """Run the RAG pipeline (retrieve + LLM) for each scenario.

    Uses the same system prompt as Baseline B so the comparison is
    apples-to-apples.  Returns results in the same format as
    load_system_results() so evaluate_system_results() can score them.
    """
    import os
    from openai import OpenAI
    from eval.baselines import CONTEXT_SYSTEM
    from eval.config import SYSTEM_MODEL, SYSTEM_BASE_URL, REPO_ROOT
    from src.rag.client import HybridRetrievalClient

    api_key = os.environ.get("GEMINI_API_KEY", "")
    llm = OpenAI(api_key=api_key, base_url=SYSTEM_BASE_URL)
    retrieval_client = HybridRetrievalClient(repo_root=REPO_ROOT)

    results = []
    for s in scenarios:
        sid = s["id"]
        question = s["question"]
        hint = _pick_source_hint(s)

        print(f"  {sid}: retrieving (hint={hint})...", end="", flush=True)
        resp = retrieval_client.retrieve(query=question, source_hint=hint, top_k=top_k)
        chunks = resp.get("chunks", [])
        print(f" {len(chunks)} chunks", end="", flush=True)

        if chunks:
            context_block = "\n\n".join(
                f"[{c['metadata']['citation']}]\n{c['text']}" for c in chunks
            )
            llm_result = llm.chat.completions.create(
                model=SYSTEM_MODEL,
                messages=[
                    {"role": "system", "content": CONTEXT_SYSTEM},
                    {"role": "user", "content": f"Source documents:\n{context_block}\n\nQuestion: {question}"},
                ],
                temperature=0,
                max_tokens=4096,
            )
            response_text = llm_result.choices[0].message.content.strip()
        else:
            response_text = ""
        print(f" -> {len(response_text)} chars")

        results.append({
            "id": sid,
            "system_output": {
                "action": "retrieve",
                "retrieval_calls": [{"query": question, "source_hint": hint, "top_k": top_k}],
                "retrieval_results": [resp],
                "constraint_result": {},
            },
            "response": response_text,
        })

    return results


def main():
    """Run the eval harness CLI."""
    parser = argparse.ArgumentParser(description="Boston Tea Party 2.0 eval harness")
    parser.add_argument(
        "--hhem-only",
        action="store_true",
        help="Legacy: skip faithfulness/API calls, run local-only metrics",
    )
    parser.add_argument("--dry-run", action="store_true", help="Load scenarios only")
    parser.add_argument(
        "--system-results", type=Path,
        help="Score precomputed system outputs from a JSON file",
    )
    parser.add_argument(
        "--pipeline", action="store_true",
        help="Run RAG pipeline end-to-end: retrieve, generate, then score",
    )
    parser.add_argument("--top-k", type=int, default=5, help="Chunks to retrieve (pipeline mode)")
    args = parser.parse_args()

    all_scenarios = load_all_scenarios()
    if not all_scenarios:
        print("No scenarios found. Add JSON files to benchmarks/")
        return

    BASELINE_TYPES = {"factual_lookup", "eligibility_determination", "calculation", None}

    if args.system_results:
        system_results = load_system_results(args.system_results)
        print(f"Loaded {len(system_results)} precomputed system results from {args.system_results.name}")
        if args.dry_run:
            print("Dry run complete.")
            return
        scored = evaluate_system_results(scenarios, system_results, hhem_only=args.hhem_only)
        summary = summarize_system(scored)
        save_results(scored, summary)
        return

    if args.pipeline:
        scenarios = [s for s in all_scenarios if s.get("question_type") in BASELINE_TYPES]
        skipped = len(all_scenarios) - len(scenarios)
        if skipped:
            print(f"Filtered to {len(scenarios)} scenarios (skipped {skipped} planning/other)")
        if args.dry_run:
            print("Dry run complete.")
            return
        print("\n--- RAG Pipeline: retrieve + generate ---")
        system_results = run_pipeline(scenarios, top_k=args.top_k)
        # Save raw outputs for reproducibility
        from datetime import datetime as _dt
        raw_path = RESULTS_DIR / f"system_outputs_{_dt.now().strftime('%Y%m%d_%H%M%S')}.json"
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump(system_results, f, indent=2, default=str)
        print(f"Raw outputs saved to {raw_path}")
        print("\n--- Scoring ---")
        scored = evaluate_system_results(scenarios, system_results, hhem_only=args.hhem_only)
        summary = summarize_system(scored)
        save_results(scored, summary)
        return

    # Default: run baselines
    scenarios = [s for s in all_scenarios if s.get("question_type") in BASELINE_TYPES]
    skipped = len(all_scenarios) - len(scenarios)
    if skipped:
        print(f"Filtered to {len(scenarios)} baseline-scorable scenarios (skipped {skipped} planning/other)")
    if args.dry_run:
        print("Dry run complete.")
        return
    scored = evaluate_baselines(scenarios, hhem_only=args.hhem_only)
    summary = summarize(scored)
    save_results(scored, summary)


if __name__ == "__main__":
    main()
