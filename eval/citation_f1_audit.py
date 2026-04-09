"""
Root-cause audit for system-mode citation F1 outcomes.

Usage:
    python -m eval.citation_f1_audit
    python -m eval.citation_f1_audit --eval-file path\\to\\eval_*.json
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from eval.config import RESULTS_DIR


def _latest_system_eval_file() -> Path:
    """Return the newest eval_*.json that contains system summary fields."""
    candidates = []
    for path in sorted(RESULTS_DIR.glob("eval_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if "system_accuracy" in payload.get("summary", {}):
            candidates.append(path)
    if not candidates:
        raise FileNotFoundError("No system eval_*.json files found in eval/results/")
    return candidates[-1]


def _mapped_retrieved_citations(system: dict) -> list[str]:
    """Return the retrieved citations that were mapped to benchmark identities."""
    mapped = []
    for detail in system.get("citation_mapping_details", []) or []:
        if detail.get("mapped") and detail.get("retrieved_citation"):
            mapped.append(detail["retrieved_citation"])
    return mapped


def _retrieved_top_citations(system: dict) -> list[str]:
    """Flatten retrieval lists into a single ordered top-citations list."""
    lists = system.get("retrieved_citation_lists", []) or []
    if not lists:
        return []
    if len(lists) == 1:
        return list(lists[0])
    merged = []
    for lst in lists:
        merged.extend(lst)
    return merged


def _claim_evidence(system: dict) -> list[dict]:
    """Extract compact claim-level evidence from citation_nli_details."""
    evidence = []
    for detail in system.get("citation_nli_details", []) or []:
        evidence.append(
            {
                "sentence": detail.get("sentence"),
                "citations_found": list(detail.get("citations_found", []) or []),
                "mapped_citations": list(detail.get("mapped_citations", []) or []),
                "supported": bool(detail.get("supported", False)),
                "citation_only_attachment": bool(detail.get("citation_only_attachment", False)),
                "list_inherited_support": bool(detail.get("list_inherited_support", False)),
                "support_method": detail.get("support_method"),
            }
        )
    return evidence


def _has_mapping_false_positive(system: dict) -> bool:
    """Detect obviously bad mappings from the recorded details."""
    for detail in system.get("citation_mapping_details", []) or []:
        if not detail.get("mapped"):
            continue
        if not detail.get("source_id_match", True):
            return True
        if not detail.get("structural_match", True):
            return True
    return False


def _primary_cause(system: dict) -> tuple[str, str]:
    """Assign one primary root cause to a system citation-F1 outcome."""
    citation_f1 = system.get("citation_f1")
    skipped = bool(system.get("citation_metrics_skipped", False))
    answer_correct = bool(system.get("answer_correct", False))
    unmapped = list(system.get("unmapped_required_citations", []) or [])
    details = list(system.get("citation_nli_details", []) or [])

    if citation_f1 is not None and citation_f1 > 0:
        return "success", "Citation F1 is nonzero for this scenario."

    if skipped and unmapped:
        return "retrieval_miss", "No retrieved citation could be mapped to the benchmark citation target."

    if _has_mapping_false_positive(system):
        return "mapping_false_positive", "A benchmark citation was mapped to a retrieved citation without a trustworthy structural match."

    if details:
        claim_rows = [d for d in details if d.get("citation_required")]
        detached_rows = [
            d for d in details
            if not d.get("citation_required") and d.get("mapped_citations")
        ]
        if detached_rows and not any(d.get("mapped_citations") for d in claim_rows):
            return (
                "citation_only_attachment_failure",
                "Mapped citations only appeared in a detached citation-only line and never attached to the claim.",
            )
        if any(d.get("citation_only_attachment") for d in claim_rows) and not any(d.get("supported") for d in claim_rows):
            return "citation_only_attachment_failure", "A citation-only attachment was attempted but did not produce support."
        if any(d.get("citations_found") or d.get("mapped_citations") for d in claim_rows):
            if not any(d.get("supported") for d in claim_rows):
                return "support_failure", "Mapped citations were present, but no supported claim was established."
        if not any(d.get("mapped_citations") for d in claim_rows):
            return "no_explicit_citation_attachment", "The answer cites sources, but no mapped citation attached to the scored claim blocks."

    if not answer_correct:
        return "answer_wrong", "The answer is materially wrong, so low citation F1 is not primarily an eval-path issue."

    return "support_failure", "Citation F1 stayed zero without retrieval miss or obvious attachment failure."


def _bucket_sets(rows: list[dict]) -> dict:
    """Group scenarios into pipeline/eval/mixed buckets."""
    pipeline = []
    eval_cases = []
    mixed = []
    for row in rows:
        cause = row["primary_cause"]
        sid = row["id"]
        answer_correct = bool(row.get("answer_correct", False))
        if cause == "retrieval_miss":
            pipeline.append(sid)
        elif cause in {"mapping_false_positive", "no_explicit_citation_attachment", "citation_only_attachment_failure"}:
            eval_cases.append(sid)
        elif cause == "support_failure":
            mixed.append(sid)
        elif cause == "answer_wrong" and not answer_correct:
            mixed.append(sid)
        elif cause == "success":
            continue
        else:
            mixed.append(sid)
    return {
        "pipeline_problem_cases": pipeline,
        "eval_problem_cases": eval_cases,
        "mixed_problem_cases": mixed,
    }


def build_audit(eval_payload: dict, eval_file: Path) -> dict:
    """Construct the citation audit artifact from a system eval payload."""
    rows = []
    for scenario in eval_payload.get("scenarios", []):
        system = scenario.get("system") or {}
        if not system:
            continue

        cause, reason = _primary_cause(system)
        row = {
            "id": scenario["id"],
            "required_citations": [d.get("required_citation") for d in system.get("citation_mapping_details", []) if d.get("required_citation")],
            "citation_existence": system.get("citation_existence"),
            "citation_f1": system.get("citation_f1"),
            "citation_recall": system.get("citation_recall"),
            "citation_precision": system.get("citation_precision"),
            "citation_mapping_applied": system.get("citation_mapping_applied", False),
            "mapped_retrieved_citations": _mapped_retrieved_citations(system),
            "unmapped_required_citations": list(system.get("unmapped_required_citations", []) or []),
            "retrieved_top_citations": _retrieved_top_citations(system),
            "primary_cause": cause,
            "primary_cause_reason": reason,
            "answer_correct": system.get("answer_correct"),
            "claim_evidence": _claim_evidence(system),
        }
        rows.append(row)

    counts = Counter(row["primary_cause"] for row in rows)
    buckets = _bucket_sets(rows)
    summary = {
        "n_scenarios": len(rows),
        "n_success": counts.get("success", 0),
        "n_retrieval_miss": counts.get("retrieval_miss", 0),
        "n_mapping_false_positive": counts.get("mapping_false_positive", 0),
        "n_no_explicit_citation_attachment": counts.get("no_explicit_citation_attachment", 0),
        "n_citation_only_attachment_failure": counts.get("citation_only_attachment_failure", 0),
        "n_support_failure": counts.get("support_failure", 0),
        "n_answer_wrong": counts.get("answer_wrong", 0),
        **buckets,
    }
    return {
        "source_eval_file": str(eval_file),
        "summary": summary,
        "scenarios": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit system citation F1 root causes")
    parser.add_argument("--eval-file", type=Path, help="Specific system eval_*.json to audit")
    args = parser.parse_args()

    eval_file = args.eval_file or _latest_system_eval_file()
    payload = json.loads(eval_file.read_text(encoding="utf-8"))
    audit = build_audit(payload, eval_file)

    print(f"Auditing: {eval_file.name}")
    summary = audit["summary"]
    print("\n--- Citation F1 Audit Summary ---")
    for key in [
        "n_scenarios",
        "n_success",
        "n_retrieval_miss",
        "n_mapping_false_positive",
        "n_no_explicit_citation_attachment",
        "n_citation_only_attachment_failure",
        "n_support_failure",
        "n_answer_wrong",
    ]:
        print(f"  {key}: {summary[key]}")
    print(f"  pipeline_problem_cases: {summary['pipeline_problem_cases']}")
    print(f"  eval_problem_cases: {summary['eval_problem_cases']}")
    print(f"  mixed_problem_cases: {summary['mixed_problem_cases']}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"citation_audit_{timestamp}.json"
    out_path.write_text(json.dumps(audit, indent=2), encoding="utf-8")
    print(f"\nAudit saved to {out_path}")


if __name__ == "__main__":
    main()
