"""
Retrieval verification runner.
Runs the golden retrieval cases through the real HybridRetrievalClient
and scores source-type consistency, tax-year validation, and provenance
completeness on every response.

Usage:
    python -m eval.retrieval_verification
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Set

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.metrics.retrieval_metrics import (
    check_provenance_completeness,
    check_source_type_consistency,
    check_tax_year_validation,
)


def _irc_sections_on_disk(irc_dir: Path) -> Set[str]:
    if not irc_dir.is_dir():
        return set()
    out: Set[str] = set()
    for p in irc_dir.glob("26_usc_*.html"):
        if "sample" in p.name.lower():
            continue
        name = p.stem.replace("26_usc_", "")
        if name:
            out.add(name)
    return out


def _should_skip_irc(case: Dict[str, Any], irc_loaded: Set[str]) -> bool:
    """Skip IRC golden cases when the required section HTML is missing."""
    expect = case.get("expect") or {}
    sec = expect.get("section_in_top3")
    if sec and str(sec) not in irc_loaded:
        return True
    return False


def _compute_locators(chunks: list[dict]) -> list[str]:
    """Compute retrieval_locator for each chunk if the locator module is available."""
    try:
        from src.rag.locator import retrieval_locator
        return [retrieval_locator((c or {}).get("metadata") or {}) for c in chunks]
    except ImportError:
        return []


def run_verification() -> dict:
    """Run all golden retrieval cases with verification checks."""
    from src.rag.client import HybridRetrievalClient

    golden_path = REPO_ROOT / "data" / "rag" / "golden_retrieval.jsonl"
    if not golden_path.exists():
        print(f"Golden retrieval file not found: {golden_path}")
        return {"error": "golden file missing"}

    lines = [ln for ln in golden_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    cases = [json.loads(ln) for ln in lines]
    irc_loaded = _irc_sections_on_disk(REPO_ROOT / "sources" / "irc")
    client = HybridRetrievalClient(repo_root=REPO_ROOT)

    results = []
    for case in cases:
        cid = case.get("id", "?")
        query = case["query"]
        hint = case.get("source_hint")
        top_k = int(case.get("top_k", 5))
        opts = case.get("options") or {}

        if _should_skip_irc(case, irc_loaded):
            results.append({"id": cid, "skipped": True, "reason": "IRC section not on disk"})
            print(f"  {cid}: SKIP (missing IRC section)")
            continue

        resp = client.retrieve(query, source_hint=hint, top_k=top_k, options=opts)
        chunks = resp.get("chunks", [])
        sources_queried = resp.get("sources_queried", [])
        requested_year = opts.get("tax_year")

        source_check = check_source_type_consistency(hint, sources_queried, chunks)
        year_check = check_tax_year_validation(chunks, requested_year, hint)
        provenance_check = check_provenance_completeness(chunks, hint)
        locators = _compute_locators(chunks)

        entry = {
            "id": cid,
            "skipped": False,
            "source_hint": hint,
            "n_chunks": len(chunks),
            "sources_queried": sources_queried,
            "source_type_consistency": source_check,
            "tax_year_validation": year_check,
            "provenance_completeness": provenance_check,
            "locators": locators,
        }
        results.append(entry)

        # Console output
        checks = []
        if not source_check.get("skipped"):
            checks.append(f"SrcType={'PASS' if source_check['passed'] else 'FAIL'}")
        if not year_check.get("skipped"):
            checks.append(f"TaxYear={'PASS' if year_check['passed'] else 'FAIL'}")
        if not provenance_check.get("skipped"):
            pct = provenance_check.get("completeness_rate", 0)
            checks.append(f"Prov={pct:.0%}")
        check_str = "  ".join(checks) if checks else "all checks skipped"
        print(f"  {cid}: {check_str}")

    summary = _compute_summary(results)
    return {"summary": summary, "cases": results}


def _compute_summary(results: list[dict]) -> dict:
    non_skipped = [r for r in results if not r.get("skipped")]
    n = len(non_skipped)

    # Source-type consistency
    src_applicable = [r for r in non_skipped if not r["source_type_consistency"].get("skipped")]
    src_passed = sum(1 for r in src_applicable if r["source_type_consistency"]["passed"])

    # Tax-year validation
    year_applicable = [r for r in non_skipped if not r["tax_year_validation"].get("skipped")]
    year_passed = sum(1 for r in year_applicable if r["tax_year_validation"]["passed"])

    # Provenance completeness
    prov_applicable = [r for r in non_skipped if not r["provenance_completeness"].get("skipped")]
    prov_passed = sum(1 for r in prov_applicable if r["provenance_completeness"]["passed"])
    prov_rates = [r["provenance_completeness"]["completeness_rate"] for r in prov_applicable]

    summary = {
        "total_cases": len(results),
        "cases_run": n,
        "cases_skipped": len(results) - n,
        # golden_retrieval is intentionally omitted here.
        # This runner checks source-type, tax-year, and provenance.
        # Golden retrieval pass/fail comes from the partner golden
        # test runner (rag_golden_test.py), not from this script.
        "source_type_consistency": {
            "applicable": len(src_applicable),
            "passed": src_passed,
            "pass_rate": src_passed / len(src_applicable) if src_applicable else None,
        },
        "tax_year_validation": {
            "applicable": len(year_applicable),
            "passed": year_passed,
            "pass_rate": year_passed / len(year_applicable) if year_applicable else None,
        },
        "provenance_completeness": {
            "applicable": len(prov_applicable),
            "all_complete": prov_passed,
            "avg_completeness": sum(prov_rates) / len(prov_rates) if prov_rates else None,
        },
    }

    print("\n--- Retrieval Verification Summary ---")
    print(f"  Cases: {n} run, {len(results) - n} skipped")
    if src_applicable:
        print(f"  Source-type consistency: {src_passed}/{len(src_applicable)} ({summary['source_type_consistency']['pass_rate']:.0%})")
    if year_applicable:
        print(f"  Tax-year validation: {year_passed}/{len(year_applicable)} ({summary['tax_year_validation']['pass_rate']:.0%})")
    if prov_applicable:
        print(f"  Provenance completeness: {prov_passed}/{len(prov_applicable)} fully complete, avg {summary['provenance_completeness']['avg_completeness']:.0%}")

    return summary


def main():
    print("--- Running Retrieval Verification ---")
    results = run_verification()

    out_dir = REPO_ROOT / "eval" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"retrieval_verification_{timestamp}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
