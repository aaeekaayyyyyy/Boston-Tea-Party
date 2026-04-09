"""
Citation F1 via NLI (DeBERTa-v3-large).
Checks whether cited passages actually entail the claims in the response.
Runs locally, no API key needed.

Implements the Citation F1 metric from the eval plan:
- Split response into blocks and sentences
- Let explicit citations govern nearby claim sentences in the same block
- Run a deterministic numeric-support heuristic for simple threshold/rate claims
- Fall back to NLI against cleaned claim sentences when the heuristic cannot decide
- Citation recall = supported citation-required sentences / total citation-required sentences
- Citation precision = necessary explicit citations / total explicit citations
- Citation F1 = harmonic mean
"""
import re

from eval.metrics.citation_utils import (
    normalize_citation_text,
    find_citations_in_sentence,
    split_prose_paragraph,
    split_list_paragraph,
    is_list_item,
    clean_hypothesis,
    is_substantive_claim,
    is_citation_only,
)
from eval.metrics.numeric_support import numeric_support_check


_model = None
_tokenizer = None

# Model: cross-encoder/nli-deberta-v3-large
# Labels: 0=contradiction, 1=entailment, 2=neutral
NLI_MODEL_NAME = "cross-encoder/nli-deberta-v3-large"
ENTAILMENT_LABEL = 1


# -- NLI model -----------------------------------------------------------------

def _load_model():
    """Lazy-load the NLI model from HuggingFace."""
    global _model, _tokenizer
    if _model is None:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        print(f"Loading {NLI_MODEL_NAME} (first time may download ~1.7GB)...")
        _tokenizer = AutoTokenizer.from_pretrained(NLI_MODEL_NAME)
        _model = AutoModelForSequenceClassification.from_pretrained(NLI_MODEL_NAME)
        _model.eval()
        print("NLI model loaded.")
    return _model, _tokenizer


def _check_entailment(premise: str, hypothesis: str) -> bool:
    """Return True if the NLI model predicts entailment."""
    import torch

    model, tokenizer = _load_model()
    inputs = tokenizer(
        premise, hypothesis,
        return_tensors="pt", truncation=True, max_length=1024, padding=True,
    )
    with torch.no_grad():
        logits = model(**inputs).logits
        predicted_class = logits.argmax(dim=-1).item()
    return predicted_class == ENTAILMENT_LABEL


# -- Block construction --------------------------------------------------------

def _build_blocks(response: str) -> list[list[dict]]:
    """
    Build citation-support blocks from the response.

    Blank lines normally start a new block, but numbered list paragraphs
    inherit the current block so a cited lead sentence can govern the list.
    """
    paragraphs = [
        p.strip() for p in re.split(r"\n\s*\n+", response.strip()) if p.strip()
    ]
    blocks: list[list[dict]] = []
    current_block: list[dict] = []

    for paragraph in paragraphs:
        is_list = is_list_item(paragraph)
        units: list[dict] = []

        if is_list:
            for item in split_list_paragraph(paragraph):
                units.append({"raw_sentence": item, "is_list_item": True})
        else:
            for sentence in split_prose_paragraph(paragraph):
                units.append({"raw_sentence": sentence, "is_list_item": False})

        if is_list and current_block:
            current_block.extend(units)
        else:
            if current_block:
                blocks.append(current_block)
            current_block = units

    if current_block:
        blocks.append(current_block)
    return blocks


def _citation_alias_map(
    required_citations: list[str],
    true_source_passages: list[dict],
) -> dict[str, list[str]]:
    """Build benchmark-citation aliases from mapped retrieved citations."""
    alias_map: dict[str, list[str]] = {citation: [] for citation in required_citations}
    for passage in true_source_passages or []:
        citation = passage.get("citation")
        if citation not in alias_map:
            continue
        aliases = alias_map[citation]
        for alias in passage.get("aliases", []) or []:
            if alias and alias not in aliases:
                aliases.append(alias)
    return alias_map


def _block_has_substantive_claim(
    block: list[dict],
    citations: list[str],
    alias_map: dict[str, list[str]] | None = None,
) -> bool:
    """Return True if the block contains at least one substantive claim."""
    for unit in block:
        if is_citation_only(unit["raw_sentence"], citations, alias_map):
            continue
        if is_substantive_claim(clean_hypothesis(unit["raw_sentence"])):
            return True
    return False


def _block_is_citation_only(
    block: list[dict],
    citations: list[str],
    alias_map: dict[str, list[str]] | None = None,
) -> bool:
    """Return True if every unit in the block is citation-only scaffolding."""
    if not block:
        return False
    has_explicit = False
    for unit in block:
        if find_citations_in_sentence(unit["raw_sentence"], citations, alias_map):
            has_explicit = True
        if not is_citation_only(unit["raw_sentence"], citations, alias_map):
            return False
    return has_explicit


def _attach_citation_only_blocks(
    blocks: list[list[dict]],
    citations: list[str],
    alias_map: dict[str, list[str]] | None = None,
) -> list[list[dict]]:
    """
    Attach citation-only blocks to the nearest adjacent substantive block.

    Citation-only blocks (e.g. trailing "(IRS Pub. 501)") are prepended to
    the target block so their citations govern nearby claims.
    """
    attachments: dict[int, list[dict]] = {}
    skipped: set[int] = set()

    for idx, block in enumerate(blocks):
        if not _block_is_citation_only(block, citations, alias_map):
            continue

        # Find nearest substantive block (prefer previous)
        prev_target = next(
            (i for i in range(idx - 1, -1, -1)
             if _block_has_substantive_claim(blocks[i], citations, alias_map)),
            None,
        )
        next_target = next(
            (i for i in range(idx + 1, len(blocks))
             if _block_has_substantive_claim(blocks[i], citations, alias_map)),
            None,
        )
        target = prev_target if prev_target is not None else next_target
        if target is None:
            continue

        for unit in block:
            attached = dict(unit)
            attached["attached_citation_only"] = True
            attached["source_block_index"] = idx
            attachments.setdefault(target, []).append(attached)
        skipped.add(idx)

    merged = []
    for idx, block in enumerate(blocks):
        if idx in skipped:
            continue
        merged_block = attachments.get(idx, []) + block
        merged.append(merged_block)
    return merged


# -- Main scoring function -----------------------------------------------------

def score_citation_f1(
    response: str,
    required_citations: list[str],
    true_source_passages: list[dict],
) -> dict:
    """
    Compute Citation F1 using block-scoped citation inheritance and NLI.

    Args:
        response: the generated answer text
        required_citations: list of citation strings that should be cited
        true_source_passages: list of dicts with "citation" and "text" keys

    Returns:
        dict with citation_recall, citation_precision, citation_f1, details
    """
    if not required_citations or not true_source_passages:
        return {
            "citation_recall": None, "citation_precision": None,
            "citation_f1": None, "details": [],
        }

    passage_lookup = {
        normalize_citation_text(p["citation"]): p["text"]
        for p in true_source_passages
    }
    citation_aliases = _citation_alias_map(required_citations, true_source_passages)

    blocks = _attach_citation_only_blocks(
        _build_blocks(response), required_citations, citation_aliases
    )

    details = []
    total_required = 0
    supported_count = 0
    total_citation_uses = 0
    necessary_citation_uses = 0

    for block_index, block_units in enumerate(blocks):
        active_citations: list[str] = []
        block_details: list[dict] = []
        active_scope_id = None
        scope_supported: dict[int, dict[str, set[int]]] = {}

        for unit_index, unit in enumerate(block_units):
            raw = unit["raw_sentence"]
            cleaned = clean_hypothesis(raw)
            cit_only = is_citation_only(raw, required_citations, citation_aliases)
            citation_required = is_substantive_claim(cleaned) and not cit_only

            explicit_found = find_citations_in_sentence(raw, required_citations, citation_aliases)
            explicit_mapped = [
                c for c in explicit_found
                if normalize_citation_text(c) in passage_lookup
            ]

            # Update active citation scope
            if explicit_mapped:
                active_citations = explicit_mapped.copy()
                active_scope_id = unit_index
                total_citation_uses += len(explicit_mapped)
                scope_supported[active_scope_id] = {
                    c: set() for c in explicit_mapped
                }

            citation_results = []
            sentence_supported = False
            support_method = "none"
            numeric_applied = False
            active_for_sentence = active_citations.copy()

            # Check support for citation-required sentences
            if citation_required and active_for_sentence:
                for citation in active_for_sentence:
                    passage = passage_lookup[normalize_citation_text(citation)]

                    # Try numeric heuristic first
                    num = numeric_support_check(passage, cleaned)
                    numeric_applied = numeric_applied or num["applied"]

                    if num["supported"]:
                        entails = True
                        method = "numeric_heuristic"
                    else:
                        entails = _check_entailment(premise=passage, hypothesis=cleaned)
                        method = "nli" if entails else "none"

                    citation_results.append({
                        "citation": citation, "entails": entails,
                        "support_method": method,
                        "numeric_heuristic_applied": num["applied"],
                    })

                    if entails:
                        sentence_supported = True
                        if support_method == "none":
                            support_method = method
                        if (active_scope_id is not None
                                and citation in scope_supported.get(active_scope_id, {})):
                            scope_supported[active_scope_id][citation].add(unit_index)

            if citation_required:
                total_required += 1
                if sentence_supported:
                    supported_count += 1

            detail = {
                "sentence": raw,
                "citation_required": citation_required,
                "citations_found": explicit_found,
                "mapped_citations": explicit_mapped,
                "has_citation": len(explicit_found) > 0,
                "has_mapped_citation": len(explicit_mapped) > 0,
                "supported": sentence_supported,
                "citation_results": citation_results,
                "cleaned_sentence": cleaned,
                "active_citations": active_for_sentence,
                "block_index": block_index,
                "scope_index": active_scope_id,
                "list_inherited_support": (
                    unit["is_list_item"] and not explicit_mapped and bool(active_for_sentence)
                ),
                "citation_only_attachment": unit.get("attached_citation_only", False),
                "support_method": support_method,
                "numeric_heuristic_applied": numeric_applied,
            }
            block_details.append(detail)
            details.append(detail)

        # Precision: check which explicit citations are necessary
        for entry in block_details:
            if not entry["mapped_citations"]:
                continue
            scope_id = entry["scope_index"]
            for citation in entry["mapped_citations"]:
                supported_units = scope_supported.get(scope_id, {}).get(citation, set())
                if supported_units:
                    necessary_citation_uses += 1

    recall = supported_count / total_required if total_required > 0 else 0.0
    precision = (
        necessary_citation_uses / total_citation_uses
        if total_citation_uses > 0 else 0.0
    )
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0 else 0.0
    )

    return {
        "citation_recall": recall,
        "citation_precision": precision,
        "citation_f1": f1,
        "details": details,
    }
