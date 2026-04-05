# RAG pipeline (`src/rag`)

`HybridRetrievalClient` implements `RetrievalClientProtocol` from `src/planning/contracts.py` (see `docs/retrieval_interface_spec.md`).

## Paths

| Source | Mechanism | Default inputs |
|--------|-----------|----------------|
| `irs_pubs` | PageIndex tree JSON + **BM25** over flattened nodes (title, trail, text) with title/trail boost | `data/rag/pageindex_irs_tree.json` — refresh with `python scripts/refresh_pageindex_tree.py` |
| `irc` | LII HTML parser + **BM25** over chunks | All `sources/irc/26_usc_*.html` (excludes `*sample*`); use `scripts/download_irc_sections.py` to add sections |
| `tax_court` | BM25 over JSONL | `data/rag/tax_court_corpus.jsonl` — see `data/rag/README.md` |

## Metadata for verification

Chunks include `citation`, `source_type`, `publication` + `publication_year` (IRS pubs), `heading_trail`, `node_id` (PageIndex or corpus `chunk_id`), `source_url` (LII canonical or opinion URL when present).

## Environment

- `PAGEINDEX_API_KEY` — required to refresh the IRS tree via API.
- `PAGEINDEX_IRS_DOC_ID` — optional; defaults to the spike doc id if unset.
- `.env` in repo root is loaded automatically (not committed).

## Usage

```python
from pathlib import Path
from src.rag.client import HybridRetrievalClient
from src.planning.agent import PlanningAgent

client = HybridRetrievalClient(repo_root=Path(".").resolve())
agent = PlanningAgent(constraint_engine=..., retrieval_client=client)
```

CLI: `python scripts/run_planning_demo.py` (hybrid) or `python scripts/run_planning_demo.py --mock`.

## Optional LLM tree search

The IRS path uses BM25 over flattened tree nodes. You can add an LLM node-picker (PageIndex cookbook pattern) before or after BM25 shortlist without changing the planning contract.
