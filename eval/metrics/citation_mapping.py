"""
Citation mapping between retrieved chunk citations and benchmark-required
citations so score_citation_f1() can operate in system mode.

Matching is intentionally conservative and source-specific:
  - IRS publications: same source ID plus distinctive heading-token alignment
  - IRC: primarily on section / subsection identity
  - Tax Court: case-name token overlap

If no safe match exists, the citation stays unmapped.
"""
from __future__ import annotations

import re

from eval.metrics.citation_utils import (
    _significant_tokens,
    extract_source_id,
    normalize_citation_text,
)

_TEXT_JACCARD_THRESHOLD = 0.3
_IRS_GENERIC_TOKENS = {
    "pub", "irs", "filing", "status", "dependents", "standard",
    "deduction", "deductions", "information", "and", "the", "of",
}


def _text_jaccard(text_a: str, text_b: str) -> float:
    """Jaccard similarity on significant normalized tokens."""
    a = _significant_tokens(normalize_citation_text(text_a))
    b = _significant_tokens(normalize_citation_text(text_b))
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _guess_source_type(citation: str, citation_norm: str, source_id: str) -> str:
    """Best-effort source type guess from the citation string."""
    if source_id.startswith("pub "):
        return "irs_pubs"
    if source_id.startswith("irc "):
        return "irc"
    if " v " in citation_norm or re.search(r"\bv\.\b", citation, flags=re.IGNORECASE):
        return "tax_court"
    return "unknown"


def _distinctive_irs_tokens(citation_norm: str, source_id: str) -> set[str]:
    """Tokens that must survive for an IRS pub heading to be considered specific."""
    tokens = set(_significant_tokens(citation_norm))
    tokens -= set(source_id.split())
    tokens -= _IRS_GENERIC_TOKENS
    return tokens


def _irs_heading_phrase(citation_norm: str, source_id: str) -> str:
    """Benchmark heading phrase after stripping the source ID prefix."""
    tail = citation_norm.strip()
    if source_id and tail.startswith(source_id):
        tail = tail[len(source_id):].strip()
    return tail


def _irs_heading_overlap(required_norm: str, candidate_norm: str, source_id: str) -> float:
    """Distinctive-token overlap for IRS publication headings."""
    required_tokens = _distinctive_irs_tokens(required_norm, source_id)
    if not required_tokens:
        return 0.0
    candidate_tokens = _significant_tokens(candidate_norm)
    return len(required_tokens & candidate_tokens) / len(required_tokens)


def _irs_structural_match(required_norm: str, candidate_norm: str, source_id: str) -> bool:
    """Require the benchmark heading phrase to appear as a contiguous tail."""
    heading_phrase = _irs_heading_phrase(required_norm, source_id)
    if not heading_phrase:
        return False
    return heading_phrase in candidate_norm


def _extract_irc_section_identity(citation: str) -> str:
    """Extract IRC section identity including simple subsections when present."""
    match = re.search(
        r"(?:IRC|26\s*U\.?\s*S\.?\s*C\.?)\s*§?\s*(\d+(?:\([a-zA-Z0-9]+\))*)",
        citation,
        flags=re.IGNORECASE,
    )
    if not match:
        return ""
    return match.group(1).lower()


def _tax_court_case_tokens(citation_norm: str) -> set[str]:
    """Tokens that identify a Tax Court case name."""
    tokens = _significant_tokens(citation_norm)
    return {t for t in tokens if t not in {"tax", "court", "memo", "tcm", "v"}}


def map_citations(
    required_citations: list[str],
    true_source_passages: list[dict],
    retrieved_passages: list[dict],
) -> dict:
    """Map retrieved passages back to benchmark citation identities."""
    if not required_citations or not retrieved_passages:
        return {
            "mapped_citation_passages": [],
            "citation_mapping_applied": False,
            "citation_mapping_details": [],
            "unmapped_required_citations": list(required_citations or []),
        }

    gold_text = {}
    for passage in true_source_passages or []:
        norm = normalize_citation_text(passage.get("citation", ""))
        if norm:
            gold_text[norm] = passage.get("text", "")

    normalized_retrieved = []
    for passage in retrieved_passages:
        citation = passage.get("citation", "")
        norm = normalize_citation_text(citation)
        source_id = extract_source_id(norm)
        normalized_retrieved.append(
            {
                "citation": citation,
                "text": passage.get("text", ""),
                "norm": norm,
                "source_id": source_id,
                "source_type": _guess_source_type(citation, norm, source_id),
                "irc_section_identity": _extract_irc_section_identity(citation),
            }
        )

    mapped_passages = []
    details = []
    unmapped = []

    for required in required_citations:
        required_norm = normalize_citation_text(required)
        source_id = extract_source_id(required_norm)
        source_type = _guess_source_type(required, required_norm, source_id)
        required_irc_identity = _extract_irc_section_identity(required)
        required_case_tokens = _tax_court_case_tokens(required_norm)
        best = None
        best_method = None
        best_evidence = None

        for candidate in normalized_retrieved:
            source_id_match = candidate["source_id"] == source_id
            heading_overlap = 0.0
            text_similarity = 0.0
            structural_match = False

            if candidate["norm"] == required_norm:
                best = candidate
                best_method = "exact_normalized"
                best_evidence = {
                    "required_norm": required_norm,
                    "retrieved_norm": candidate["norm"],
                    "source_type": source_type,
                    "source_id_match": source_id_match,
                    "heading_overlap": 1.0,
                    "text_similarity": 1.0,
                    "structural_match": True,
                }
                break

            if source_type == "irs_pubs":
                if not source_id_match:
                    continue
                heading_overlap = _irs_heading_overlap(required_norm, candidate["norm"], source_id)
                structural_match = _irs_structural_match(required_norm, candidate["norm"], source_id)
                if structural_match:
                    best = candidate
                    best_method = f"irs_heading_match({heading_overlap:.2f})"
                    best_evidence = {
                        "required_norm": required_norm,
                        "retrieved_norm": candidate["norm"],
                        "source_type": source_type,
                        "source_id_match": source_id_match,
                        "heading_overlap": heading_overlap,
                        "text_similarity": 0.0,
                        "structural_match": structural_match,
                    }
                    break
                if required_norm in gold_text:
                    text_similarity = _text_jaccard(gold_text[required_norm], candidate["text"])
                    section_family_match = bool(
                        _significant_tokens(required_norm) & _significant_tokens(candidate["norm"])
                    )
                    if section_family_match and heading_overlap > 0.0 and text_similarity >= _TEXT_JACCARD_THRESHOLD:
                        if best is None or (best_evidence and text_similarity > best_evidence["text_similarity"]):
                            best = candidate
                            best_method = f"irs_text_fallback({text_similarity:.2f})"
                            best_evidence = {
                                "required_norm": required_norm,
                                "retrieved_norm": candidate["norm"],
                                "source_type": source_type,
                                "source_id_match": source_id_match,
                                "heading_overlap": heading_overlap,
                                "text_similarity": text_similarity,
                                "structural_match": False,
                            }

            elif source_type == "irc":
                if candidate["source_type"] != "irc":
                    continue
                structural_match = (
                    bool(required_irc_identity)
                    and candidate["irc_section_identity"] == required_irc_identity
                )
                if structural_match:
                    best = candidate
                    best_method = "irc_section_identity"
                    best_evidence = {
                        "required_norm": required_norm,
                        "retrieved_norm": candidate["norm"],
                        "source_type": source_type,
                        "source_id_match": source_id_match,
                        "heading_overlap": 0.0,
                        "text_similarity": 0.0,
                        "structural_match": structural_match,
                    }
                    break

            elif source_type == "tax_court":
                candidate_case_tokens = _tax_court_case_tokens(candidate["norm"])
                if required_case_tokens and required_case_tokens <= candidate_case_tokens:
                    best = candidate
                    best_method = "tax_court_case_name"
                    best_evidence = {
                        "required_norm": required_norm,
                        "retrieved_norm": candidate["norm"],
                        "source_type": source_type,
                        "source_id_match": source_id_match,
                        "heading_overlap": 0.0,
                        "text_similarity": 0.0,
                        "structural_match": True,
                    }
                    break

        if best is not None:
            mapped_passages.append({"citation": required, "text": best["text"]})
            details.append(
                {
                    "required_citation": required,
                    "retrieved_citation": best["citation"],
                    "match_method": best_method,
                    "mapped": True,
                    **(best_evidence or {}),
                }
            )
        else:
            unmapped.append(required)
            details.append(
                {
                    "required_citation": required,
                    "retrieved_citation": None,
                    "match_method": None,
                    "mapped": False,
                    "required_norm": required_norm,
                    "retrieved_norm": None,
                    "source_type": source_type,
                    "source_id_match": False,
                    "heading_overlap": 0.0,
                    "text_similarity": 0.0,
                    "structural_match": False,
                }
            )

    return {
        "mapped_citation_passages": mapped_passages,
        "citation_mapping_applied": len(mapped_passages) > 0,
        "citation_mapping_details": details,
        "unmapped_required_citations": unmapped,
    }
