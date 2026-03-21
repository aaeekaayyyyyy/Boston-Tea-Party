"""
Load benchmark scenarios from JSON files.
Validates that required fields are present.
"""
import json
from pathlib import Path
from typing import Optional

REQUIRED_FIELDS = {"id", "question", "answer", "required_citations", "constraint_result"}


def load_scenarios(path: Path) -> list[dict]:
    """Load benchmark scenarios from a JSON file. Returns list of scenario dicts."""
    with open(path, "r", encoding="utf-8") as f:
        scenarios = json.load(f)

    if not isinstance(scenarios, list):
        raise ValueError(f"Expected a JSON array in {path}, got {type(scenarios).__name__}")

    validated = []
    for i, s in enumerate(scenarios):
        missing = REQUIRED_FIELDS - set(s.keys())
        if missing:
            print(f"  Warning: scenario {i} (id={s.get('id', '?')}) missing fields: {missing}")
        validated.append(s)

    print(f"Loaded {len(validated)} scenarios from {path.name}")
    return validated


def load_all_scenarios(benchmarks_dir: Optional[Path] = None) -> list[dict]:
    """Load all .json files from the benchmarks directory."""
    if benchmarks_dir is None:
        from eval.config import BENCHMARKS_DIR
        benchmarks_dir = BENCHMARKS_DIR

    all_scenarios = []
    for f in sorted(benchmarks_dir.glob("*.json")):
        all_scenarios.extend(load_scenarios(f))

    print(f"Total: {len(all_scenarios)} scenarios")
    return all_scenarios
