from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from rank_bm25 import BM25Okapi

from .bm25_rank import tokenize_doc


class TaxCourtBM25Index:
    """BM25 over a JSONL corpus: one object per line with text, case_name, year, docket."""

    def __init__(self, corpus_path: Path) -> None:
        self.corpus_path = corpus_path
        self._docs: List[str] = []
        self._meta: List[Dict[str, Any]] = []
        self._bm25: Optional[BM25Okapi] = None
        self._load()

    def _load(self) -> None:
        if not self.corpus_path.exists():
            return
        for line in self.corpus_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            text = (obj.get("text") or "").strip()
            if not text:
                continue
            self._docs.append(text)
            self._meta.append(
                {
                    "case_name": obj.get("case_name", "Unknown"),
                    "year": obj.get("year"),
                    "docket": obj.get("docket"),
                    "chunk_id": obj.get("chunk_id"),
                    "source_url": obj.get("source_url"),
                }
            )
        if self._docs:
            tokenized = [tokenize_doc(d) for d in self._docs]
            self._bm25 = BM25Okapi(tokenized)

    def search(self, query: str, top_k: int) -> List[Tuple[float, str, Dict[str, Any]]]:
        if not self._bm25 or not self._docs:
            return []
        q_tokens = tokenize_doc(query)
        if not q_tokens:
            return []
        scores = self._bm25.get_scores(q_tokens)
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        return [(float(scores[i]), self._docs[i], self._meta[i]) for i in ranked]
