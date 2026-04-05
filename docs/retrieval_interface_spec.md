# Retrieval Interface Spec — RAG Pipeline ↔ Planning Agent

**Purpose**: Contract between the RAG pipeline (Ayushman) and the planning agent / orchestration layer (Anthony) so Week 2 implementation stays aligned. All retrieval paths expose the same interface.

---

## 1. Input

The planning agent calls the retrieval layer with:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | yes | Natural-language question or topic (e.g. "What are the tax brackets for head of household?"). |
| `source_hint` | string or null | no | Optional hint: `"irc"`, `"irs_pubs"`, `"tax_court"`, or `null` for auto-routing. When set, retrieval may restrict to that source type. |
| `top_k` | int | no | Max number of results to return. Default: 5. |
| `options` | dict | no | See **section 1.1 Options** below (tax year, publication, IRC hints, rerank flags). |

**Example**

```json
{
  "query": "Who qualifies for head of household filing status?",
  "source_hint": "irs_pubs",
  "top_k": 5
}
```

### 1.1 Options (`options` dict)

| Key | Type | Applies to | Description |
|-----|------|------------|-------------|
| `tax_year` | int | `irs_pubs` | Sets `publication_year` on IRS metadata/citations (align with the indexed Pub PDF). |
| `irs_publication` | string | `irs_pubs` | Publication number for citation text (e.g. `"501"`, `"526"`). Does not swap the cached PageIndex tree by itself—refresh `pageindex_irs_tree.json` when the underlying PDF changes. |
| `irc_sections_hint` | list of string | `irc` | Section numbers (e.g. `["63","2"]`) to **boost** in ranking when the planner knows which IRC provisions matter. |
| `active_rules` | list of string | all | Echoed from the constraint engine for logging/traceability (e.g. `["filing_status","standard_deduction"]`). |
| `rule_id` | string or null | all | Primary rule driving this retrieval call (e.g. `"filing_status"`). |
| `irs_llm_rerank` | bool | `irs_pubs` | If `true` (default when unset and `OPENAI_API_KEY` is set), BM25 shortlists ~18 nodes then an LLM picks final `node_id`s. Set `false` for deterministic eval. Disable globally with env `DISABLE_IRS_LLM_RERANK=1`. |
| `irs_bm25_shortlist` | int | `irs_pubs` | Shortlist size before LLM pick (default 18, max 40). |

---

## 2. Output

A single response shape regardless of backend (tree-based vs BM25):

| Field | Type | Description |
|-------|------|-------------|
| `chunks` | list | Ranked list of retrieval results (see chunk shape below). |
| `strategy` | string | Which path was used: `"tree"` or `"bm25"`. |
| `sources_queried` | list of string | Source types actually queried, e.g. `["irc", "irs_pubs"]`. |
| `retrieval_empty` | bool | `true` when `chunks` is empty—agents must not treat this as a successful grounding pass. |
| `retrieval_message` | string or null | When `retrieval_empty` is `true`, human-readable reason (missing corpus, API misconfig, etc.). When results exist, usually `null`. |

**Chunk shape** (each element of `chunks`):

| Field | Type | Description |
|-------|------|-------------|
| `text` | string | The retrieved passage (plain text). |
| `metadata` | object | Source metadata for citations and verification (see below). |
| `score` | float or null | Relevance score when available (BM25 score for `tax_court`; also BM25-style scores for `irc` / flattened IRS tree nodes). |

**Metadata** (minimum required for verification layer):

| Field | Type | Description |
|-------|------|-------------|
| `source_type` | string | `"irc"` \| `"irs_pubs"` \| `"tax_court"`. |
| `citation` | string | Human-readable citation, e.g. `"26 USC § 1(c)"`, `"IRS Pub. 501 (2024), Ch. 1"`, `"Smith v. Commissioner (2020)"`. |
| `section` | string or null | IRC section number; null for IRS pubs / tax court unless mapped. |
| `publication_year` | int or null | Tax year for IRS publications or opinion year for Tax Court; null for IRC (statute). |
| `publication` | string or null | IRS publication number (e.g. `"501"`) when `source_type` is `irs_pubs`; else null. |
| `case_name` | string or null | Tax Court case name; null for IRC/IRS Pubs. |
| `page_index` | int or null | Page number if available (e.g. from PageIndex). |
| `subsection` | string or null | IRC subsection letter when applicable. |
| `heading_trail` | string or null | IRS Pub: heading path (`Title > Section`); IRC: parsed heading labels from LII. |
| `node_id` | string or null | PageIndex node id for IRS tree chunks; Tax Court: optional `chunk_id` from corpus. |
| `source_url` | string or null | Canonical LII URL for IRC; optional opinion URL for Tax Court. |

**Example response**

```json
{
  "retrieval_empty": false,
  "retrieval_message": null,
  "chunks": [
    {
      "text": "There is hereby imposed on the taxable income of every head of a household (as defined in section 2(b)) a tax determined in accordance with the following table...",
      "metadata": {
        "source_type": "irc",
        "citation": "26 USC § 1(b)",
        "section": "1",
        "subsection": "b",
        "publication_year": null,
        "publication": null,
        "case_name": null,
        "page_index": null,
        "heading_trail": "Heads of households",
        "node_id": null,
        "source_url": "https://www.law.cornell.edu/uscode/text/26/1"
      },
      "score": null
    }
  ],
  "strategy": "tree",
  "sources_queried": ["irc", "irs_pubs"]
}
```

---

## 3. Routing

- **Tree path** (IRC + IRS Publications): Used when `source_hint` is `"irc"` or `"irs_pubs"`, or when `source_hint` is null and the router (or agent) decides the query is about statute/guidance.
- **BM25 path** (Tax Court): Used when `source_hint` is `"tax_court"`, or when the query is about case law / judicial interpretation.
- **Both**: Orchestration may call retrieval twice (once per path) and merge/sort if needed; the interface is per-call, so the agent can issue multiple calls with different `source_hint` values.

---

## 4. Python stub (for integration)

```python
from typing import Optional

def retrieve(
    query: str,
    source_hint: Optional[str] = None,  # "irc" | "irs_pubs" | "tax_court" | None
    top_k: int = 5,
    options: Optional[dict] = None,
) -> dict:
    """
    Returns:
        {
            "chunks": [{"text": str, "metadata": dict, "score": float|None}],
            "strategy": "tree" | "bm25",
            "sources_queried": [str]
        }
    """
    ...
```

---

## 5. Sync with Anthony

- **Planning agent** sends `query`, `source_hint`, and `options` populated from the constraint engine (`active_rules`, `rule_id`, `irc_sections_hint`, `irs_publication`, `tax_year`) so retrieval is not limited to keyword auto-routing.
- **Verification layer** (Francesco) should use `metadata.citation`, `metadata.source_type`, and for IRS pubs `metadata.publication` + `metadata.publication_year` + `metadata.heading_trail`; use `metadata.node_id` (PageIndex or corpus `chunk_id`) and `metadata.source_url` when present to align claims to a stable locator.
- **Normalized locator:** `from src.rag.locator import retrieval_locator` — `retrieval_locator(chunk["metadata"])` returns one pipe-delimited string per source type so checkers need not re-parse citations.

### Minimum metadata checklist (verification)

| `source_type` | Check |
|----------------|--------|
| `irs_pubs` | `publication`, `publication_year`, `heading_trail`, `node_id` |
| `irc` | `citation`, `section`, `source_url` when available |
| `tax_court` | `case_name`, `publication_year` (year), `docket`, `chunk_id` via `node_id` |

- **Demo UI** can display `citation` and link to source (e.g. Cornell LII for IRC, IRS.gov for Pubs).

## 6. Eval

- Golden queries: `data/rag/golden_retrieval.jsonl`; runner: `python eval/rag_golden_test.py`. Track pass/fail when changing BM25, LLM rerank, or corpora.
- **Ops:** Never commit `.env` or API keys (`.gitignore` includes `.env`); rotate any key that was exposed.
