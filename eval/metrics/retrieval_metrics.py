"""
Pure retrieval metrics for ranked citation lists.
"""
from __future__ import annotations

from eval.metrics.citation_utils import normalize_citation_text


def precision_at_k(retrieved: list[str], gold: list[str], k: int) -> float:
    """Compute precision over the first k retrieved citations."""
    if k <= 0:
        return 0.0

    top_k = [normalize_citation_text(citation) for citation in (retrieved or [])[:k]]
    if not top_k:
        return 0.0

    gold_set = {
        normalize_citation_text(citation)
        for citation in (gold or [])
        if normalize_citation_text(citation)
    }
    hits = sum(1 for citation in top_k if citation and citation in gold_set)
    return hits / len(top_k)


def mrr(retrieved: list[str], gold: list[str]) -> float:
    """Compute reciprocal rank of the first relevant retrieved citation."""
    gold_set = {
        normalize_citation_text(citation)
        for citation in (gold or [])
        if normalize_citation_text(citation)
    }
    if not gold_set:
        return 0.0

    for index, citation in enumerate(retrieved or [], start=1):
        if normalize_citation_text(citation) in gold_set:
            return 1.0 / index
    return 0.0
