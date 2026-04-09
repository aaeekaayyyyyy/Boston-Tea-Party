"""Lightweight checks for HybridRetrievalClient data dependencies (no network)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List


def hybrid_retrieval_readiness(repo_root: Path) -> Dict[str, Any]:
    """
    Inspect on-disk assets used by HybridRetrievalClient.
    """
    root = repo_root.resolve()
    tree = root / "data" / "rag" / "pageindex_irs_tree.json"
    irc_dir = root / "sources" / "irc"
    tc = root / "data" / "rag" / "tax_court_corpus.jsonl"

    irc_html_count = len(list(irc_dir.glob("*.html"))) if irc_dir.is_dir() else 0
    tc_ok = tc.is_file() and tc.stat().st_size > 0

    issues: List[str] = []
    if not tree.is_file():
        issues.append(
            "IRS publication tree cache missing at data/rag/pageindex_irs_tree.json. "
            "Run: python scripts/refresh_pageindex_tree.py (needs PAGEINDEX_API_KEY) or supply a cache file."
        )
    elif tree.stat().st_size < 100:
        issues.append("pageindex_irs_tree.json looks empty or truncated.")

    if irc_html_count == 0:
        issues.append(
            "No IRC HTML in sources/irc/. Run: python scripts/download_irc_sections.py"
        )

    if not tc_ok:
        issues.append(
            "Tax Court corpus missing or empty at data/rag/tax_court_corpus.jsonl. "
            "Add lines or run scripts/ingest_tax_court_line.py."
        )

    try:
        tree_rel = str(tree.relative_to(root))
    except ValueError:
        tree_rel = str(tree)

    return {
        "repo_root": str(root),
        "pageindex_cache": {
            "path": tree_rel,
            "exists": tree.is_file(),
            "size_bytes": tree.stat().st_size if tree.is_file() else 0,
        },
        "irc": {"html_file_count": irc_html_count, "dir": "sources/irc"},
        "tax_court": {
            "path": "data/rag/tax_court_corpus.jsonl",
            "nonempty": tc_ok,
        },
        "ready": len(issues) == 0,
        "issues": issues,
    }
