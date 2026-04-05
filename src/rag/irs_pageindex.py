from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .bm25_rank import BM25Ranker, apply_title_trail_boost

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DOC_ID = "pi-cmma55t2r04700jo9fdj0dzaw"


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

    @staticmethod
    def _shallow_penalty(row: Dict[str, Any]) -> float:
        """Down-rank root-like or very short nodes so generic title matches lose to real sections."""
        trail = (row.get("trail") or "").strip()
        depth = trail.count(" > ") + (1 if (row.get("title") or "").strip() else 0)
        text = (row.get("text") or "").strip()
        if depth <= 1 and len(text) < 80:
            return 0.35
        if depth <= 1 and len(text) < 180:
            return 0.62
        if len(text) < 40:
            return 0.5
        return 1.0

    def _llm_pick_node_ids(
        self, query: str, candidates: List[Dict[str, Any]], top_k: int
    ) -> Optional[List[str]]:
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key or os.environ.get("DISABLE_IRS_LLM_RERANK", "").strip() in (
            "1",
            "true",
            "yes",
        ):
            return None
        try:
            from openai import OpenAI
        except ImportError:
            return None

        slim: List[Dict[str, Any]] = []
        for r in candidates:
            nid = r.get("node_id")
            if not nid:
                continue
            slim.append(
                {
                    "node_id": str(nid),
                    "title": (r.get("title") or "")[:240],
                    "trail": (r.get("trail") or "")[:500],
                }
            )
        if not slim:
            return None

        client = OpenAI(api_key=api_key)
        user_payload = json.dumps(slim, ensure_ascii=False, indent=2)
        prompt = (
            "You pick which IRS publication outline nodes best answer the user's tax question. "
            "Prefer specific substantive sections over generic chapter intros or publication titles.\n"
            f"Question: {query}\n\n"
            f"Nodes (JSON):\n{user_payload}\n\n"
            f'Respond with JSON only: {{"node_ids": ["<id>", ...]}} '
            f"with at most {top_k} ids in best-first order. Only use node_id values from the list."
        )
        try:
            comp = client.chat.completions.create(
                model=os.environ.get("IRS_LLM_RERANK_MODEL", "gpt-4o-mini"),
                messages=[
                    {
                        "role": "system",
                        "content": "You output compact JSON only. No markdown.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                response_format={"type": "json_object"},
            )
            raw = (comp.choices[0].message.content or "").strip()
            data = json.loads(raw)
            ids = data.get("node_ids")
            if not isinstance(ids, list):
                return None
            out: List[str] = []
            for x in ids:
                if isinstance(x, str) and re.match(r"^[A-Za-z0-9._-]+$", x):
                    out.append(x)
            return out[: max(top_k, 1)]
        except Exception:
            return None

    def search(
        self,
        query: str,
        top_k: int,
        options: Optional[Dict[str, Any]] = None,
    ) -> List[Tuple[float, Dict[str, Any]]]:
        rows = self.ensure_flat()
        if not rows:
            return []
        opts = options or {}
        shortlist_n = int(opts.get("irs_bm25_shortlist", 18))
        shortlist_n = max(shortlist_n, top_k + 3)
        shortlist_n = min(shortlist_n, 40)

        docs = [f"{r['title']} {r['trail']} {r['text']}" for r in rows]
        ranker = BM25Ranker(docs)
        pool = max(shortlist_n * 3, shortlist_n + 12, len(rows))
        hits = ranker.search(query, min(pool, len(rows)))
        titles = [r["title"] for r in rows]
        trails = [r["trail"] for r in rows]
        hits = apply_title_trail_boost(query, hits, titles, trails, boost=1.4)

        adjusted: List[Tuple[int, float]] = []
        for i, sc in hits:
            pen = self._shallow_penalty(rows[i])
            adjusted.append((i, sc * pen))
        adjusted.sort(key=lambda t: t[1], reverse=True)

        shortlist_rows: List[Dict[str, Any]] = []
        shortlist_scores: List[float] = []
        seen_i: set[int] = set()
        for i, sc in adjusted:
            if i in seen_i:
                continue
            seen_i.add(i)
            shortlist_rows.append(rows[i])
            shortlist_scores.append(sc)
            if len(shortlist_rows) >= shortlist_n:
                break

        use_llm = opts.get("irs_llm_rerank")
        if use_llm is None:
            use_llm = True
        ordered_rows: List[Dict[str, Any]] = []
        ordered_scores: List[float] = []
        if use_llm:
            picked = self._llm_pick_node_ids(query, shortlist_rows, top_k)
            if picked:
                by_id = {str(r.get("node_id")): r for r in shortlist_rows if r.get("node_id")}
                sc_by_id = {
                    str(r.get("node_id")): s
                    for r, s in zip(shortlist_rows, shortlist_scores)
                    if r.get("node_id")
                }
                used: set[str] = set()
                rank = 0.0
                for nid in picked:
                    row = by_id.get(str(nid))
                    if not row or str(nid) in used:
                        continue
                    used.add(str(nid))
                    rank += 1.0
                    ordered_rows.append(row)
                    ordered_scores.append(1000.0 / rank)
                    if len(ordered_rows) >= top_k:
                        break
                for r, sc in zip(shortlist_rows, shortlist_scores):
                    if len(ordered_rows) >= top_k:
                        break
                    nid = str(r.get("node_id") or "")
                    if nid and nid not in used:
                        used.add(nid)
                        ordered_rows.append(r)
                        ordered_scores.append(sc)

        if not ordered_rows:
            for i, sc in adjusted:
                ordered_rows.append(rows[i])
                ordered_scores.append(sc)
                if len(ordered_rows) >= top_k:
                    break

        out: List[Tuple[float, Dict[str, Any]]] = []
        for row, sc in zip(ordered_rows, ordered_scores):
            out.append((sc, row))
            if len(out) >= top_k:
                break
        return out
