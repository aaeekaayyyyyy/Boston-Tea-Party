#!/usr/bin/env python3
"""
Download the full PageIndex tree for an IRS publication document and save to
data/rag/pageindex_irs_tree.json (overwrites bundled sample).

Requires PAGEINDEX_API_KEY. Uses PAGEINDEX_IRS_DOC_ID if set, else default spike doc id.
Optional: submit sources/irs_pubs/p501_sample.pdf if doc is not ready (set SUBMIT_PDF=1).

Run from repo root: python scripts/refresh_pageindex_tree.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "rag" / "pageindex_irs_tree.json"
DEFAULT_DOC = "pi-cmma55t2r04700jo9fdj0dzaw"


def load_dotenv() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def main() -> int:
    load_dotenv()
    sys.path.insert(0, str(ROOT))
    api_key = os.environ.get("PAGEINDEX_API_KEY", "").strip()
    if not api_key:
        print("Set PAGEINDEX_API_KEY (e.g. in .env) to refresh the tree.")
        return 1
    try:
        from pageindex import PageIndexClient
    except ImportError:
        print("Install pageindex: pip install pageindex")
        return 1

    doc_id = os.environ.get("PAGEINDEX_IRS_DOC_ID", DEFAULT_DOC).strip()
    client = PageIndexClient(api_key=api_key)

    if not client.is_retrieval_ready(doc_id) and os.environ.get("SUBMIT_PDF") == "1":
        pdf = ROOT / "sources" / "irs_pubs" / "p501_sample.pdf"
        if pdf.exists():
            doc_id = client.submit_document(str(pdf))["doc_id"]
            print("Submitted PDF, new doc_id:", doc_id)
            for _ in range(50):
                if client.is_retrieval_ready(doc_id):
                    break
                time.sleep(2)
        else:
            print("SUBMIT_PDF=1 but PDF missing:", pdf)
            return 1

    if not client.is_retrieval_ready(doc_id):
        print("Document not ready:", doc_id)
        print("Wait and retry, or set SUBMIT_PDF=1 with p501_sample.pdf present.")
        return 1

    tree = client.get_tree(doc_id, node_summary=True)
    if tree.get("status") != "completed" or not tree.get("result"):
        print("Unexpected response:", tree.get("status"), list(tree.keys()))
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {"result": tree["result"], "doc_id": doc_id}
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("Wrote", OUT, "nodes at root:", len(tree["result"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
