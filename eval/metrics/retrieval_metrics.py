"""
Retrieval metrics and verification checks.
- Precision@k and MRR for ranked citation lists
- Source-type consistency, tax-year validation, provenance completeness
"""
from __future__ import annotations

from eval.metrics.citation_utils import normalize_citation_text


# -- Ranked retrieval metrics --------------------------------------------------

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


# -- Retrieval-side verification checks ----------------------------------------

def check_source_type_consistency(
    source_hint: str | None,
    sources_queried: list[str],
) -> dict:
    """
    Verify that retrieved sources match the requested source type.

    Returns dict with pass/fail, expected, actual, and skip status.
    """
    if source_hint is None:
        return {"passed": True, "skipped": True, "reason": "no source_hint specified"}

    queried = set(sources_queried or [])
    if source_hint in queried:
        return {"passed": True, "skipped": False, "expected": source_hint, "actual": list(queried)}

    return {
        "passed": False,
        "skipped": False,
        "expected": source_hint,
        "actual": list(queried),
        "reason": f"expected {source_hint!r} in sources_queried but got {list(queried)}",
    }


def check_tax_year_validation(
    chunks: list[dict],
    requested_tax_year: int | None,
    source_hint: str | None,
) -> dict:
    """
    Verify that IRS publication chunks carry the correct publication_year.
    Only applies when source_hint is "irs_pubs" and a tax_year was requested.

    Returns dict with pass/fail, mismatched chunks, and skip status.
    """
    if source_hint != "irs_pubs" or requested_tax_year is None:
        return {"passed": True, "skipped": True, "reason": "not an IRS pubs query with tax_year"}

    mismatched = []
    for i, chunk in enumerate(chunks or []):
        meta = (chunk or {}).get("metadata") or {}
        pub_year = meta.get("publication_year")
        if pub_year is not None and int(pub_year) != int(requested_tax_year):
            mismatched.append({
                "chunk_index": i,
                "citation": meta.get("citation", ""),
                "publication_year": pub_year,
                "expected_year": requested_tax_year,
            })

    return {
        "passed": len(mismatched) == 0,
        "skipped": False,
        "requested_tax_year": requested_tax_year,
        "total_chunks": len(chunks or []),
        "mismatched_chunks": mismatched,
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

    Returns dict with completeness counts and per-chunk detail.
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
