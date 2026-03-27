"""
Constraint accuracy scorer.
Loads rule benchmark cases from src/benchmarks/,
runs them through the rule engine adapter, and reports metrics.

Reports:
- Per-case pass/fail (exact match of all expected keys)
- Key-level accuracy
- Element-level precision, recall, F1 (handles both boolean and list values)
- Per-domain breakdown

Usage:
    python -m eval.constraint_benchmark           # run all cases
    python -m eval.constraint_benchmark --domain filing_status  # one domain
"""
import argparse
from datetime import datetime
import json

from eval.config import REPO_ROOT
from eval.rule_engine import run_rule_case

INDEX_PATH = REPO_ROOT / "src" / "benchmarks" / "index.json"
_MISSING_PREDICTION = "__missing_prediction__"


def load_benchmark_index() -> list[dict]:
    """Load the benchmark index that points to the rule benchmark files."""
    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        index = json.load(f)
    return index["files"]


def load_benchmark_cases(file_entry: dict) -> tuple[list[dict], list[str]]:
    """Load all cases and referenced rule files for a benchmark entry."""
    path = REPO_ROOT / file_entry["path"]
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    cases = data["cases"]
    if "rules_file" in data:
        rules_files = [data["rules_file"]]
    elif "rules_files" in data:
        rules_files = data["rules_files"]
    else:
        rules_files = []

    return cases, rules_files


def _to_element_set(value, *, missing: bool = False) -> set:
    """Convert a value to a set of elements for P/R/F1 computation."""
    if missing:
        return {_MISSING_PREDICTION}
    if isinstance(value, list):
        return set(str(v) for v in value)
    elif isinstance(value, bool):
        # For booleans: True = {"true"}, False = {"false"}
        return {str(value).lower()}
    elif value is None:
        return set()
    else:
        return {str(value)}


def diff_expected(predicted: dict, expected: dict) -> dict:
    """
    Compare predicted state against expected outputs.
    Computes both key-level accuracy and element-level P/R/F1.
    """
    details = []
    keys_correct = 0
    keys_wrong = 0

    # Element-level confusion counts across all keys
    total_tp = 0
    total_fp = 0
    total_fn = 0

    for key, expected_val in expected.items():
        predicted_present = key in predicted
        predicted_val = predicted.get(key)

        # Key-level: exact match (sort lists for comparison)
        if isinstance(expected_val, list) and isinstance(predicted_val, list):
            key_match = sorted(str(v) for v in expected_val) == sorted(str(v) for v in predicted_val)
        else:
            key_match = predicted_val == expected_val

        if key_match:
            keys_correct += 1
        else:
            keys_wrong += 1

        # Element-level: set-based P/R for this key
        expected_set = _to_element_set(expected_val)
        predicted_set = _to_element_set(predicted_val, missing=not predicted_present)

        tp = len(expected_set & predicted_set)
        fp = len(predicted_set - expected_set)
        fn = len(expected_set - predicted_set)

        total_tp += tp
        total_fp += fp
        total_fn += fn

        details.append({
            "key": key,
            "expected": expected_val,
            "predicted": predicted_val,
            "match": key_match,
            "tp": tp, "fp": fp, "fn": fn,
        })

    return {
        "keys_checked": keys_correct + keys_wrong,
        "keys_correct": keys_correct,
        "keys_wrong": keys_wrong,
        "tp": total_tp,
        "fp": total_fp,
        "fn": total_fn,
        "details": details,
    }


def run_constraint_benchmark(domain_filter: str | None = None) -> dict:
    """Run the standalone rule benchmark, optionally filtered to one domain."""
    index_entries = load_benchmark_index()
    all_results = []

    for entry in index_entries:
        if domain_filter and entry["domain"] != domain_filter:
            continue

        cases, rules_files = load_benchmark_cases(entry)

        if not rules_files:
            print(f"  Skipping {entry['domain']}: no rules_files specified")
            continue

        for case in cases:
            case_id = case["case_id"]
            facts = case["facts"]
            expected = case["expected"]

            try:
                predicted = run_rule_case(facts, rules_files)
                diff = diff_expected(predicted, expected)
                result = {
                    "case_id": case_id,
                    "domain": entry["domain"],
                    "description": case.get("description", ""),
                    "pass": diff["keys_wrong"] == 0,
                    "keys_checked": diff["keys_checked"],
                    "keys_correct": diff["keys_correct"],
                    "keys_wrong": diff["keys_wrong"],
                    "tp": diff["tp"],
                    "fp": diff["fp"],
                    "fn": diff["fn"],
                    "details": diff["details"],
                    "error": None,
                }
            except Exception as e:
                result = {
                    "case_id": case_id,
                    "domain": entry["domain"],
                    "description": case.get("description", ""),
                    "pass": False,
                    "keys_checked": len(expected),
                    "keys_correct": 0,
                    "keys_wrong": len(expected),
                    "tp": 0,
                    "fp": 0,
                    "fn": sum(len(_to_element_set(v)) for v in expected.values()),
                    "details": [],
                    "error": str(e),
                }

            all_results.append(result)

            status = "PASS" if result["pass"] else "FAIL"
            print(f"  {status}  {case_id}: {result['keys_correct']}/{result['keys_checked']} keys", end="")
            if result["error"]:
                print(f"  ERROR: {result['error']}", end="")
            elif not result["pass"]:
                wrong_keys = [d for d in result["details"] if not d["match"]]
                for wk in wrong_keys:
                    print(f"\n         {wk['key']}: expected={wk['expected']} got={wk['predicted']}", end="")
            print()

    summary = _compute_summary(all_results)
    return {"summary": summary, "cases": all_results}


def _compute_summary(results: list[dict]) -> dict:
    """Aggregate case-level rule benchmark results into summary metrics."""
    n_cases = len(results)
    if n_cases == 0:
        return {"n_cases": 0}

    cases_passed = sum(1 for r in results if r["pass"])
    total_keys = sum(r["keys_checked"] for r in results)
    correct_keys = sum(r["keys_correct"] for r in results)

    # Element-level precision / recall / F1 across all cases
    total_tp = sum(r["tp"] for r in results)
    total_fp = sum(r["fp"] for r in results)
    total_fn = sum(r["fn"] for r in results)

    precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
    recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    case_accuracy = cases_passed / n_cases
    key_accuracy = correct_keys / total_keys if total_keys > 0 else 0.0

    # Per-domain breakdown
    domains = {}
    for r in results:
        d = r["domain"]
        if d not in domains:
            domains[d] = {"cases": 0, "passed": 0, "keys": 0, "keys_correct": 0,
                          "tp": 0, "fp": 0, "fn": 0}
        domains[d]["cases"] += 1
        domains[d]["passed"] += 1 if r["pass"] else 0
        domains[d]["keys"] += r["keys_checked"]
        domains[d]["keys_correct"] += r["keys_correct"]
        domains[d]["tp"] += r["tp"]
        domains[d]["fp"] += r["fp"]
        domains[d]["fn"] += r["fn"]

    for d in domains:
        s = domains[d]
        s["case_accuracy"] = s["passed"] / s["cases"]
        s["key_accuracy"] = s["keys_correct"] / s["keys"] if s["keys"] > 0 else 0.0
        s["precision"] = s["tp"] / (s["tp"] + s["fp"]) if (s["tp"] + s["fp"]) > 0 else 0.0
        s["recall"] = s["tp"] / (s["tp"] + s["fn"]) if (s["tp"] + s["fn"]) > 0 else 0.0
        s["f1"] = (2 * s["precision"] * s["recall"] / (s["precision"] + s["recall"])
                   if (s["precision"] + s["recall"]) > 0 else 0.0)

    summary = {
        "n_cases": n_cases,
        "cases_passed": cases_passed,
        "case_accuracy": case_accuracy,
        "total_keys": total_keys,
        "correct_keys": correct_keys,
        "key_accuracy": key_accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "per_domain": domains,
    }

    print("\n--- Constraint Benchmark Summary ---")
    print(f"  Cases:     {cases_passed}/{n_cases} passed ({case_accuracy:.1%})")
    print(f"  Keys:      {correct_keys}/{total_keys} correct ({key_accuracy:.1%})")
    print(f"  Precision: {precision:.3f}")
    print(f"  Recall:    {recall:.3f}")
    print(f"  F1:        {f1:.3f}")
    for d, stats in domains.items():
        print(f"  {d}: {stats['passed']}/{stats['cases']} cases, "
              f"P={stats['precision']:.3f} R={stats['recall']:.3f} F1={stats['f1']:.3f}")

    return summary


def main():
    """Run the constraint benchmark CLI and save a JSON report."""
    parser = argparse.ArgumentParser(description="Run constraint engine benchmarks")
    parser.add_argument("--domain", type=str, default=None,
                        help="Filter to a specific domain (e.g., filing_status, dependency)")
    args = parser.parse_args()

    print("--- Running Constraint Benchmark ---")
    results = run_constraint_benchmark(domain_filter=args.domain)

    out_dir = REPO_ROOT / "eval" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"constraint_{timestamp}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
