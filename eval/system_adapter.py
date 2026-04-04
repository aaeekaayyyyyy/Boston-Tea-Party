"""
Helpers for adapting precomputed system outputs into eval-ready inputs.
"""
from __future__ import annotations


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


def adapt_system_output(system_result: dict, scenario: dict) -> dict:
    """Normalize one saved system result into the inputs used by the eval harness."""
    system_output = system_result.get("system_output", {}) or {}
    retrieval_results = list(system_output.get("retrieval_results", []) or [])

    return {
        "response": system_result.get("response"),
        "contexts": extract_contexts(retrieval_results),
        "citation_passages": extract_citation_passages(retrieval_results),
        "retrieved_citation_lists": extract_retrieved_citation_lists(retrieval_results),
        "constraint_output": dict(system_output.get("constraint_result", {}) or {}),
        "gold_constraint": dict(scenario.get("constraint_result", {}) or {}),
        "strategy_metadata": extract_strategy_metadata(retrieval_results),
        "required_citations": list(scenario.get("required_citations", []) or []),
    }
