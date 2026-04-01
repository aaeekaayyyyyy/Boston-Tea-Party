from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DOC_ID = "pi-cmma55t2r04700jo9fdj0dzaw"


def _tokenize(s: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z]{2,}", s.lower()))


def _score_query(query: str, title: str, text: str, trail: str) -> float:
    q = _tokenize(query)
    if not q:
        return 0.0
    blob = _tokenize(f"{title} {text} {trail}")
    return len(q & blob) / len(q)


def flatten_pageindex_tree(
    nodes: List[Dict[str, Any]],
    trail_titles: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Flatten nested PageIndex tree nodes into retrievable rows."""
    if trail_titles is None:
        trail_titles = []
    out: List[Dict[str, Any]] = []
    for n in nodes:
        title = (n.get("title") or "").strip()
        trail = trail_titles + ([title] if title else [])
        text = (n.get("text") or n.get("summary") or n.get("prefix_summary") or "").strip()
        out.append(
            {
                "node_id": n.get("node_id"),
                "page_index": n.get("page_index"),
                "title": title,
                "text": text[:12000],
                "trail": " > ".join(t for t in trail if t),
            }
        )
        kids = n.get("nodes") or []
        if kids:
            out.extend(flatten_pageindex_tree(kids, trail))
    return out


def load_tree_from_cache(path: Path) -> Optional[List[Dict[str, Any]]]:
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and "result" in raw:
        return raw["result"]
    if isinstance(raw, list):
        return raw
    return None


class IRSPublicationRetriever:
    """
    IRS Publication retrieval via PageIndex tree (API or JSON cache).
    Enriches chunks with publication number, tax year, and human-readable citation.
    """

    def __init__(
        self,
        *,
        publication: str = "501",
        publication_year: int = 2025,
        pdf_path: Optional[Path] = None,
        cache_path: Optional[Path] = None,
        doc_id: Optional[str] = None,
    ) -> None:
        self.publication = publication
        self.publication_year = publication_year
        self.pdf_path = pdf_path
        self.cache_path = cache_path or REPO_ROOT / "data" / "rag" / "pageindex_irs_tree.json"
        self.doc_id = doc_id or os.environ.get("PAGEINDEX_IRS_DOC_ID") or DEFAULT_DOC_ID
        self._flat: Optional[List[Dict[str, Any]]] = None
        self._last_error: Optional[str] = None

    def _try_api(self) -> Optional[List[Dict[str, Any]]]:
        api_key = os.environ.get("PAGEINDEX_API_KEY", "").strip()
        if not api_key:
            self._last_error = "PAGEINDEX_API_KEY not set"
            return None
        try:
            from pageindex import PageIndexClient
        except ImportError:
            self._last_error = "pageindex package not installed"
            return None

        client = PageIndexClient(api_key=api_key)
        if self.doc_id and client.is_retrieval_ready(self.doc_id):
            tree = client.get_tree(self.doc_id, node_summary=True)
            if tree.get("status") == "completed" and tree.get("result"):
                return tree["result"]

        if self.pdf_path and self.pdf_path.exists():
            new_id = client.submit_document(str(self.pdf_path))["doc_id"]
            self.doc_id = new_id
            for _ in range(45):
                if client.is_retrieval_ready(new_id):
                    break
                time.sleep(2)
            tree = client.get_tree(new_id, node_summary=True)
            if tree.get("status") == "completed" and tree.get("result"):
                return tree["result"]

        self._last_error = "PageIndex tree not ready or submit failed"
        return None

    def ensure_flat(self) -> List[Dict[str, Any]]:
        if self._flat is not None:
            return self._flat

        cached = load_tree_from_cache(self.cache_path)
        if cached is not None:
            self._flat = flatten_pageindex_tree(cached)
            return self._flat

        api_result = self._try_api()
        if api_result is not None:
            self._flat = flatten_pageindex_tree(api_result)
            try:
                self.cache_path.parent.mkdir(parents=True, exist_ok=True)
                self.cache_path.write_text(
                    json.dumps({"result": api_result}, indent=2),
                    encoding="utf-8",
                )
            except OSError:
                pass
            return self._flat

        self._flat = []
        return self._flat

    def citation_for(self, row: Dict[str, Any]) -> str:
        trail = row.get("trail") or row.get("title") or "Publication"
        return f"IRS Pub. {self.publication} ({self.publication_year}), {trail}"

    def search(self, query: str, top_k: int) -> List[Tuple[float, Dict[str, Any]]]:
        rows = self.ensure_flat()
        if not rows:
            return []
        scored: List[Tuple[float, Dict[str, Any]]] = []
        for row in rows:
            s = _score_query(query, row["title"], row["text"], row["trail"])
            scored.append((s, row))
        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:top_k]
        if top and top[0][0] == 0:
            return scored[:top_k]
        return [x for x in top if x[0] > 0] or top
