"""
Helpers for adapting precomputed system outputs into eval-ready inputs.
"""
from __future__ import annotations

import re

from eval.metrics.citation_mapping import map_citations


def extract_contexts(retrieval_results: list[dict]) -> list[str]:
    """Flatten chunk texts from retrieval results, preserving first occurrence order."""
    contexts = []
    seen = set()
    for result in retrieval_results or []:
        for chunk in result.get("chunks", []) or []:
            text = (chunk or {}).get("text")
            if not text or text in seen:
                continue
            seen.add(text)
            contexts.append(text)
    return contexts


def extract_citation_passages(retrieval_results: list[dict]) -> list[dict]:
    """Flatten retrieval chunks into benchmark-style citation/text passage pairs."""
    passages = []
    seen = set()
    for result in retrieval_results or []:
        for chunk in result.get("chunks", []) or []:
            metadata = (chunk or {}).get("metadata", {}) or {}
            citation = metadata.get("citation")
            text = (chunk or {}).get("text")
            if not citation or not text:
                continue
            key = (citation, text)
            if key in seen:
                continue
            seen.add(key)
            passages.append({"citation": citation, "text": text})
    return passages


def extract_retrieved_citation_lists(retrieval_results: list[dict]) -> list[list[str]]:
    """Return ordered citation lists, one per retrieval call."""
    citation_lists = []
    for result in retrieval_results or []:
        citations = []
        for chunk in result.get("chunks", []) or []:
            metadata = (chunk or {}).get("metadata", {}) or {}
            citation = metadata.get("citation")
            if citation:
                citations.append(citation)
        citation_lists.append(citations)
    return citation_lists


def extract_strategy_metadata(retrieval_results: list[dict]) -> list[dict]:
    """Return strategy and source metadata for each retrieval call."""
    metadata = []
    for result in retrieval_results or []:
        metadata.append(
            {
                "strategy": result.get("strategy"),
                "sources_queried": list(result.get("sources_queried", []) or []),
            }
        )
    return metadata


def _citation_aliases(required_citation: str, retrieved_citation: str) -> list[str]:
    """Derive conservative answer-side aliases for a mapped retrieved citation."""
    aliases = []
    if retrieved_citation:
        aliases.append(retrieved_citation)

        # For IRS pub tree citations, also allow shorter source+tail forms.
        if ">" in retrieved_citation and re.search(r"\bpub\.?\s*\d+\b", retrieved_citation, flags=re.IGNORECASE):
            parts = [part.strip(" .") for part in retrieved_citation.split(">") if part.strip()]
            source_match = re.match(r"^(.*?pub\.?\s*\d+(?:\s*\(\d{4}\))?)", parts[0], flags=re.IGNORECASE)
            source_prefix = source_match.group(1).strip() if source_match else ""
            if source_prefix:
                aliases.append(source_prefix)
            if source_prefix and len(parts) >= 2:
                aliases.append(f"{source_prefix}, {parts[-1]}")
            if source_prefix and len(parts) >= 3:
                aliases.append(f"{source_prefix}, {parts[-2]} > {parts[-1]}")

    seen = set()
    unique = []
    for alias in aliases:
        norm = re.sub(r"\s+", " ", alias or "").strip()
        if not norm or norm.lower() == required_citation.lower() or norm.lower() in seen:
            continue
        seen.add(norm.lower())
        unique.append(norm)
    return unique


def adapt_system_output(system_result: dict, scenario: dict) -> dict:
    """Normalize one saved system result into the inputs used by the eval harness."""
    system_output = system_result.get("system_output", {}) or {}
    retrieval_results = list(system_output.get("retrieval_results", []) or [])
    required_citations = list(scenario.get("required_citations", []) or [])
    citation_passages = extract_citation_passages(retrieval_results)
    mapping = map_citations(
        required_citations,
        list(scenario.get("true_source_passages", []) or []),
        citation_passages,
    )
    aliases_by_required = {}
    for detail in mapping["citation_mapping_details"]:
        required = detail.get("required_citation")
        retrieved = detail.get("retrieved_citation")
        if not required or not retrieved or not detail.get("mapped"):
            continue
        aliases_by_required[required] = _citation_aliases(required, retrieved)

    mapped_citation_passages = []
    for passage in mapping["mapped_citation_passages"]:
        mapped = dict(passage)
        mapped["aliases"] = aliases_by_required.get(passage.get("citation"), [])
        mapped_citation_passages.append(mapped)

    return {
        "response": system_result.get("response"),
        "contexts": extract_contexts(retrieval_results),
        "citation_passages": citation_passages,
        "mapped_citation_passages": mapped_citation_passages,
        "citation_mapping_applied": mapping["citation_mapping_applied"],
        "citation_mapping_details": mapping["citation_mapping_details"],
        "unmapped_required_citations": mapping["unmapped_required_citations"],
        "retrieved_citation_lists": extract_retrieved_citation_lists(retrieval_results),
        "constraint_output": dict(system_output.get("constraint_result", {}) or {}),
        "gold_constraint": dict(scenario.get("constraint_result", {}) or {}),
        "strategy_metadata": extract_strategy_metadata(retrieval_results),
        "required_citations": required_citations,
    }
