#!/usr/bin/env python3
"""
Smoke test: HybridRetrievalClient all paths (irs_pubs, irc, tax_court, auto-routing).

Run from repo root: python eval/rag_smoke_test.py
"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.rag.client import HybridRetrievalClient
from src.rag.irc_parser import load_irc_nodes_from_dir
from src.rag.irs_pageindex import IRSPublicationRetriever


def main() -> None:
    c = HybridRetrievalClient(repo_root=ROOT)

    r = c.retrieve(
        "head of household filing status",
        source_hint="irs_pubs",
        top_k=3,
        options={"tax_year": 2025, "irs_llm_rerank": False},
    )
    assert r["sources_queried"] == ["irs_pubs"] and len(r["chunks"]) >= 1
    assert r.get("retrieval_empty") is False
    assert "retrieval_message" in r
    m0 = r["chunks"][0]["metadata"]
    assert m0["publication"] == "501" and m0["publication_year"] == 2025
    assert m0.get("heading_trail") and m0.get("node_id")

    r2 = c.retrieve("standard deduction", source_hint="irc", top_k=2)
    assert r2["sources_queried"] == ["irc"] and len(r2["chunks"]) >= 1
    assert all(x["metadata"]["source_type"] == "irc" for x in r2["chunks"])

    r3 = c.retrieve("charitable contribution", source_hint="tax_court", top_k=2)
    assert r3["strategy"] == "bm25" and r3["sources_queried"] == ["tax_court"]

    r4 = c.retrieve("tax court opinion commissioner", source_hint=None, top_k=2)
    assert r4["sources_queried"] == ["tax_court"]

    r5 = c.retrieve("internal revenue code section", source_hint=None, top_k=2)
    assert "irc" in r5["sources_queried"]

    r6 = c.retrieve("filing status dependents", source_hint=None, top_k=4)
    assert set(r6["sources_queried"]) >= {"irs_pubs", "irc"}

    nodes = load_irc_nodes_from_dir(ROOT / "sources" / "irc")
    assert len(nodes) >= 1

    irs = IRSPublicationRetriever(cache_path=ROOT / "data" / "rag" / "pageindex_irs_tree.json")
    flat = irs.ensure_flat()
    assert len(flat) >= 1

    print("rag_smoke_test: ok")


if __name__ == "__main__":
    main()
