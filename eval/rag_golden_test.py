#!/usr/bin/env python3
"""
Golden retrieval eval: hit@3-style checks from data/rag/golden_retrieval.jsonl.

Run from repo root: python eval/rag_golden_test.py
Skips IRC expectations when the section HTML is not present under sources/irc/.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Set

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.rag.client import HybridRetrievalClient


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


def _heading_blob(meta: Dict[str, Any]) -> str:
    return " ".join(
        str(x).lower()
        for x in (meta.get("heading_trail"), meta.get("citation"))
        if x
    )


def _chunk_text_blob(chunk: Dict[str, Any]) -> str:
    """Heading/citation plus start of passage (Pub 501 often mentions topics in body text)."""
    meta = chunk.get("metadata") or {}
    head = _heading_blob(meta)
    body = (chunk.get("text") or "")[:1200].lower()
    return f"{head} {body}".strip()


def _check_case(
    case: Dict[str, Any],
    resp: Dict[str, Any],
    irc_loaded: Set[str],
) -> tuple[bool, str]:
    cid = case.get("id", "?")
    ex = case.get("expect") or {}

    if "response_keys" in ex:
        keys = ex["response_keys"]
        missing = [k for k in keys if k not in resp]
        if missing:
            return False, f"{cid}: missing response keys {missing}"
        return True, f"{cid}: ok"

    if ex.get("sources_include"):
        want = ex["sources_include"]
        if want not in (resp.get("sources_queried") or []):
            return False, f"{cid}: expected sources_queried to include {want!r}"
        return True, f"{cid}: ok"

    if ex.get("min_chunks"):
        if len(resp.get("chunks") or []) < int(ex["min_chunks"]):
            return False, f"{cid}: expected at least {ex['min_chunks']} chunks"
        return True, f"{cid}: ok"

    eval_top = int(case.get("eval_top_n", 3))
    top = (resp.get("chunks") or [])[:eval_top]
    if ex.get("section_in_top3"):
        sec = str(ex["section_in_top3"])
        if sec not in irc_loaded:
            return True, f"{cid}: skip (no sources/irc/26_usc_{sec}.html)"
        got = [c.get("metadata", {}).get("section") for c in top]
        if sec not in got:
            return False, f"{cid}: section {sec} not in top-{len(top)} metadata sections {got}"
        return True, f"{cid}: ok"

    if ex.get("heading_substrings_any"):
        if not top:
            return False, f"{cid}: no chunks"
        blob = " ".join(_chunk_text_blob(c) for c in top)
        subs = [s.lower() for s in ex["heading_substrings_any"]]
        if not any(s in blob for s in subs):
            return False, f"{cid}: no heading match in top-{len(top)}: {blob[:200]!r}"
        return True, f"{cid}: ok"

    if ex.get("case_name_substrings_any"):
        if not top:
            return False, f"{cid}: no chunks"
        names = " ".join(
            str(c.get("metadata", {}).get("case_name") or "").lower() for c in top
        )
        subs = [s.lower() for s in ex["case_name_substrings_any"]]
        if not any(s in names for s in subs):
            return False, f"{cid}: case_name match failed in top-{len(top)}"
        return True, f"{cid}: ok"

    if ex.get("metadata_publication"):
        want = str(ex["metadata_publication"])
        pubs = [str(c.get("metadata", {}).get("publication") or "") for c in top]
        if want not in pubs:
            return False, f"{cid}: expected publication {want!r} in top-{len(top)}, got {pubs}"
        return True, f"{cid}: ok"

    return False, f"{cid}: unknown expect block {ex!r}"


def main() -> int:
    golden_path = ROOT / "data" / "rag" / "golden_retrieval.jsonl"
    lines = [ln for ln in golden_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    cases = [json.loads(ln) for ln in lines]

    irc_loaded = _irc_sections_on_disk(ROOT / "sources" / "irc")
    client = HybridRetrievalClient(repo_root=ROOT)

    failed = 0
    skipped = 0
    passed = 0
    for case in cases:
        q = case["query"]
        hint = case.get("source_hint")
        top_k = int(case.get("top_k", 5))
        opts = case.get("options") or {}
        resp = client.retrieve(q, source_hint=hint, top_k=top_k, options=opts)

        ok, msg = _check_case(case, resp, irc_loaded)
        if msg.startswith(f"{case.get('id')}: skip"):
            skipped += 1
            print(msg)
            continue
        if ok:
            passed += 1
            print(msg)
        else:
            failed += 1
            print("FAIL:", msg)

    print(
        f"\nGolden summary: passed={passed} failed={failed} skipped={skipped} total={len(cases)}"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
