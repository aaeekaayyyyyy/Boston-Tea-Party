"""
Retrieval metrics and verification checks.

Two tiers of retrieval scoring:
  - Section-level (strict): full normalized citation must match.
  - Source-level (loose):  only the source ID (e.g. 'pub 501') must match.
Both are reported separately so the presentation never overstates precision.
"""
from __future__ import annotations

from eval.metrics.citation_utils import (
    normalize_citation_text, extract_source_id, _significant_tokens,
)


# -- Ranked retrieval metrics (strict, section-level via token containment) ----

def _section_match(retrieved_norm: str, gold_norm: str) -> bool:
    """All significant gold tokens appear in the retrieved citation."""
    gold_tokens = _significant_tokens(gold_norm)
    if not gold_tokens:
        return False
    return gold_tokens <= _significant_tokens(retrieved_norm)


def precision_at_k(retrieved: list[str], gold: list[str], k: int) -> float:
    """Section-level precision over the first k retrieved citations."""
    if k <= 0:
        return 0.0
    top_k = [normalize_citation_text(c) for c in (retrieved or [])[:k]]
    if not top_k:
        return 0.0
    gold_norms = [normalize_citation_text(c) for c in (gold or []) if normalize_citation_text(c)]
    hits = sum(
        1 for c in top_k
        if c and any(_section_match(c, g) for g in gold_norms)
    )
    return hits / len(top_k)


def mrr(retrieved: list[str], gold: list[str]) -> float:
    """Section-level MRR: reciprocal rank of the first token-set match."""
    gold_norms = [normalize_citation_text(c) for c in (gold or []) if normalize_citation_text(c)]
    if not gold_norms:
        return 0.0
    for index, c in enumerate(retrieved or [], start=1):
        r_norm = normalize_citation_text(c)
        if any(_section_match(r_norm, g) for g in gold_norms):
            return 1.0 / index
    return 0.0


# -- Ranked retrieval metrics (loose, source-level) ----------------------------

def _source_matches(retrieved_norm: str, gold_norm: str) -> bool:
    """Does the retrieved citation share a source ID with the gold citation?"""
    if retrieved_norm == gold_norm:
        return True
    return extract_source_id(retrieved_norm) == extract_source_id(gold_norm)


def source_precision_at_k(retrieved: list[str], gold: list[str], k: int) -> float:
    """Source-level precision: counts a hit if the source ID matches."""
    if k <= 0:
        return 0.0
    top_k = [normalize_citation_text(c) for c in (retrieved or [])[:k]]
    if not top_k:
        return 0.0
    gold_norms = [normalize_citation_text(c) for c in (gold or []) if normalize_citation_text(c)]
    hits = sum(1 for c in top_k if c and any(_source_matches(c, g) for g in gold_norms))
    return hits / len(top_k)


def source_mrr(retrieved: list[str], gold: list[str]) -> float:
    """Source-level MRR: reciprocal rank of the first source-ID match."""
    gold_norms = [normalize_citation_text(c) for c in (gold or []) if normalize_citation_text(c)]
    if not gold_norms:
        return 0.0
    for index, c in enumerate(retrieved or [], start=1):
        r_norm = normalize_citation_text(c)
        if any(_source_matches(r_norm, g) for g in gold_norms):
            return 1.0 / index
    return 0.0


# -- Retrieval-side verification checks ----------------------------------------

def check_source_type_consistency(
    source_hint: str | None,
    sources_queried: list[str],
    chunks: list[dict] | None = None,
) -> dict:
    """
    Verify that retrieved sources match the requested source type.
    """
    if source_hint is None:
        return {"passed": True, "skipped": True, "reason": "no source_hint specified"}

    queried = set(sources_queried or [])
    chunk_source_types = []
    mismatched_chunk_types = []
    for i, chunk in enumerate(chunks or []):
        metadata = (chunk or {}).get("metadata") or {}
        chunk_source_type = metadata.get("source_type")
        if chunk_source_type is None:
            continue
        chunk_source_types.append(chunk_source_type)
        if chunk_source_type != source_hint:
            mismatched_chunk_types.append(
                {
                    "chunk_index": i,
                    "source_type": chunk_source_type,
                }
            )

    if source_hint in queried and not mismatched_chunk_types:
        return {
            "passed": True,
            "skipped": False,
            "expected": source_hint,
            "actual": list(queried),
            "chunk_source_types": chunk_source_types,
        }

    reasons = []
    if source_hint not in queried:
        reasons.append(f"expected {source_hint!r} in sources_queried but got {list(queried)}")
    if mismatched_chunk_types:
        reasons.append(f"found chunk source_type mismatches: {mismatched_chunk_types}")
    return {
        "passed": False,
        "skipped": False,
        "expected": source_hint,
        "actual": list(queried),
        "chunk_source_types": chunk_source_types,
        "mismatched_chunk_types": mismatched_chunk_types,
        "reason": "; ".join(reasons),
    }


def check_tax_year_validation(
    chunks: list[dict],
    requested_tax_year: int | None,
    source_hint: str | None,
) -> dict:
    """
    Verify that IRS publication chunks carry the correct publication_year.
    Only applies when source_hint is "irs_pubs" and a tax_year was requested.

    NOTE: Chunks with missing publication_year are counted separately as
    'year_missing' rather than silently passing.
    """
    if source_hint != "irs_pubs" or requested_tax_year is None:
        return {"passed": True, "skipped": True, "reason": "not an IRS pubs query with tax_year"}

    mismatched = []
    year_missing = 0
    for i, chunk in enumerate(chunks or []):
        meta = (chunk or {}).get("metadata") or {}
        pub_year = meta.get("publication_year")
        if pub_year is None:
            year_missing += 1
        elif int(pub_year) != int(requested_tax_year):
            mismatched.append({
                "chunk_index": i,
                "citation": meta.get("citation", ""),
                "publication_year": pub_year,
                "expected_year": requested_tax_year,
            })

    return {
        "passed": len(mismatched) == 0 and year_missing == 0,
        "skipped": False,
        "requested_tax_year": requested_tax_year,
        "total_chunks": len(chunks or []),
        "mismatched_chunks": mismatched,
        "year_missing": year_missing,
    }


def check_provenance_completeness(
    chunks: list[dict],
    source_type: str | None,
) -> dict:
    """
    Check whether chunks carry the minimum metadata fields for their source type.

    Required fields per source_type (from data/rag/README.md):
        irs_pubs: publication, publication_year, heading_trail, node_id
        irc: citation, section
        tax_court: case_name, publication_year, node_id
    """
    REQUIRED = {
        "irs_pubs": ["publication", "publication_year", "heading_trail", "node_id"],
        "irc": ["citation", "section"],
        "tax_court": ["case_name", "publication_year", "node_id"],
    }

    if source_type is None or source_type not in REQUIRED:
        return {"passed": True, "skipped": True, "reason": f"no required fields defined for {source_type!r}"}

    required_fields = REQUIRED[source_type]
    complete = 0
    incomplete = 0
    details = []

    for i, chunk in enumerate(chunks or []):
        meta = (chunk or {}).get("metadata") or {}
        missing = [f for f in required_fields if not meta.get(f)]
        if missing:
            incomplete += 1
            details.append({"chunk_index": i, "missing_fields": missing})
        else:
            complete += 1

    total = complete + incomplete
    return {
        "passed": incomplete == 0,
        "skipped": False,
        "source_type": source_type,
        "complete": complete,
        "incomplete": incomplete,
        "total": total,
        "completeness_rate": complete / total if total > 0 else 1.0,
        "incomplete_details": details,
    }
