#!/usr/bin/env python3
"""
Append one validated Tax Court corpus line to data/rag/tax_court_corpus.jsonl.

Interactive: run with no args and paste JSON on one line, or pass JSON as argv.

Example:
  python scripts/ingest_tax_court_line.py '{"text":"...","case_name":"X v. Commissioner","year":2020,"docket":"1-19"}'
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "data" / "rag" / "tax_court_corpus.jsonl"
REQUIRED = {"text", "case_name"}


def validate(obj: dict) -> None:
    missing = REQUIRED - set(obj.keys())
    if missing:
        raise ValueError(f"Missing keys: {missing}")
    if not str(obj.get("text", "")).strip():
        raise ValueError("text must be non-empty")


def main() -> int:
    if len(sys.argv) > 1:
        line = " ".join(sys.argv[1:])
    else:
        print("Paste one JSON object on a single line, then Enter:")
        line = sys.stdin.readline()
    line = line.strip()
    if not line:
        print("Empty input")
        return 1
    obj = json.loads(line)
    if not isinstance(obj, dict):
        print("JSON must be an object")
        return 1
    validate(obj)
    CORPUS.parent.mkdir(parents=True, exist_ok=True)
    with CORPUS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    print("Appended to", CORPUS)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (json.JSONDecodeError, ValueError) as e:
        print("Error:", e)
        raise SystemExit(1)
