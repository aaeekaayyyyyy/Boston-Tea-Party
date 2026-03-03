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
| `options` | dict | no | Future extensibility (e.g. tax_year for IRS Pubs). |

**Example**

```json
{
  "query": "Who qualifies for head of household filing status?",
  "source_hint": "irs_pubs",
  "top_k": 5
}
```

---

## 2. Output

A single response shape regardless of backend (tree-based vs BM25):

| Field | Type | Description |
|-------|------|-------------|
| `chunks` | list | Ranked list of retrieval results (see chunk shape below). |
| `strategy` | string | Which path was used: `"tree"` or `"bm25"`. |
| `sources_queried` | list of string | Source types actually queried, e.g. `["irc", "irs_pubs"]`. |

**Chunk shape** (each element of `chunks`):

| Field | Type | Description |
|-------|------|-------------|
| `text` | string | The retrieved passage (plain text). |
| `metadata` | object | Source metadata for citations and verification (see below). |
| `score` | float or null | Relevance score if available (e.g. BM25 score); null for tree retrieval. |

**Metadata** (minimum required for verification layer):

| Field | Type | Description |
|-------|------|-------------|
| `source_type` | string | `"irc"` \| `"irs_pubs"` \| `"tax_court"`. |
| `citation` | string | Human-readable citation, e.g. `"26 USC § 1(c)"`, `"IRS Pub. 501 (2024), Ch. 1"`, `"Smith v. Commissioner (2020)"`. |
| `section` | string or null | IRC section or IRS Pub section identifier; null for tax court. |
| `publication_year` | int or null | Tax year or publication year; null for IRC (statute). |
| `case_name` | string or null | Tax Court case name; null for IRC/IRS Pubs. |
| `page_index` | int or null | Page number if available (e.g. from PageIndex). |

**Example response**

```json
{
  "chunks": [
    {
      "text": "There is hereby imposed on the taxable income of every head of a household (as defined in section 2(b)) a tax determined in accordance with the following table...",
      "metadata": {
        "source_type": "irc",
        "citation": "26 USC § 1(b)",
        "section": "1",
        "subsection": "b",
        "publication_year": null,
        "case_name": null,
        "page_index": 1
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

- **Planning agent** sends `query` (and optionally `source_hint`) when it needs authoritative support for an answer or to resolve a constraint.
- **Verification layer** (Francesco) can use `metadata.citation` and `metadata.source_type` to check that generated answers cite these chunks.
- **Demo UI** can display `citation` and link to source (e.g. Cornell LII for IRC, IRS.gov for Pubs).

If you want to extend the contract (e.g. filters by tax year, or a separate "retrieve by section ID" call), we can add that in Week 2 and keep this doc updated.
