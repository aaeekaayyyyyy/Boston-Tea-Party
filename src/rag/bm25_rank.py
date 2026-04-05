from __future__ import annotations

import re
from typing import List, Sequence, Tuple

from rank_bm25 import BM25Okapi


def tokenize_doc(s: str) -> List[str]:
    return re.findall(r"[a-zA-Z0-9]+", s.lower())


class BM25Ranker:
    """BM25 over pre-tokenized or raw documents; returns (index, score) pairs."""

    def __init__(self, documents: Sequence[str]) -> None:
        self._docs = list(documents)
        self._tok = [tokenize_doc(d) for d in self._docs]
        self._bm25 = BM25Okapi(self._tok) if self._docs else None

    def search(self, query: str, top_k: int) -> List[Tuple[int, float]]:
        if not self._bm25 or not self._docs:
            return []
        q = tokenize_doc(query)
        if not q:
            return []
        scores = self._bm25.get_scores(q)
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        return [(i, float(scores[i])) for i in ranked]


def apply_title_trail_boost(
    query: str,
    indices_scores: List[Tuple[int, float]],
    titles: Sequence[str],
    trails: Sequence[str],
    boost: float = 1.35,
) -> List[Tuple[int, float]]:
    """Up-rank rows whose title or trail contains a significant query token."""
    q_terms = {t for t in tokenize_doc(query) if len(t) > 3}
    if not q_terms:
        return indices_scores
    out: List[Tuple[int, float]] = []
    for i, sc in indices_scores:
        title = titles[i].lower() if i < len(titles) else ""
        trail = trails[i].lower() if i < len(trails) else ""
        mult = 1.0
        for term in q_terms:
            if term in title:
                mult = max(mult, boost)
            elif term in trail:
                mult = max(mult, boost * 0.92)
        out.append((i, sc * mult))
    out.sort(key=lambda x: x[1], reverse=True)
    return out
