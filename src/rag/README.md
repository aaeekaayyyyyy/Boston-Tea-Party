# RAG pipeline (`src/rag`)

`HybridRetrievalClient` implements `RetrievalClientProtocol` from `src/planning/contracts.py` (see `docs/retrieval_interface_spec.md`).

## Paths

| Source | Mechanism | Default inputs |
|--------|-----------|----------------|
| `irs_pubs` | PageIndex-style tree (JSON cache or live API) | `data/rag/pageindex_irs_tree.json`, optional `sources/irs_pubs/p501_sample.pdf` |
| `irc` | Cornell LII HTML parser | `sources/irc/26_usc_1.html` |
| `tax_court` | BM25 (`rank-bm25`) | `data/rag/tax_court_corpus.jsonl` |

## Environment

- `PAGEINDEX_API_KEY` — refresh tree from API when cache is missing or you call submit.
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

The IRS path uses lexical scoring over flattened tree nodes. You can replace `IRSPublicationRetriever.search` with an LLM node-picker (PageIndex cookbook pattern) without changing the planning contract.
