# Scripts — Boston Tea Party 2.0

- **`download_samples.py`**: Download one representative sample of each source type (IRC, IRS Pub, Tax Court) into `sources/`. Run from repo root: `python scripts/download_samples.py`.
  - If you get SSL certificate errors, ensure Python can verify HTTPS (e.g. on macOS run **Install Certificates.command** from your Python app, or use a venv with `certifi`). Alternatively, save the samples manually from the URLs in the script.
- A minimal IRC sample is provided at `sources/irc/26_usc_1_sample.html` for local testing and the PageIndex spike if live download fails.
- **`run_planning_demo.py`**: Planning agent demo. Default uses `HybridRetrievalClient` (`src/rag/`). Use `--mock` for the old stub retriever.
- **`pageindex_spike.py`**: One-off PageIndex tree generation spike (see `docs/pageindex_spike_report.md`).
- **`refresh_pageindex_tree.py`**: Fetch full PageIndex tree into `data/rag/pageindex_irs_tree.json` (needs `PAGEINDEX_API_KEY`).
- **`download_irc_sections.py`**: Download LII HTML for Title 26 sections into `sources/irc/`. Default sections match constraint-engine citations (`1`, `2`, `63`, `68`, `151`, `152`, `170`, `6012`, `6013`, `7703`); pass section numbers as args to override.
- **`ingest_tax_court_line.py`**: Append one validated JSONL line to `data/rag/tax_court_corpus.jsonl`.
- **Retrieval golden set**: `python eval/rag_golden_test.py` (queries in `data/rag/golden_retrieval.jsonl`).
- **`serve_story_demo.py`**: FastAPI app: **SimpleConstraintEngine** + **PlanningAgent** + **HybridRetrievalClient** by default. Serves **React** from `frontend/dist` when built; if `dist/` is missing, `/` shows build instructions (API and `/docs` still work).
  - **Production-style:** `cd frontend && npm install && npm run build && cd .. && python scripts/serve_story_demo.py` → http://127.0.0.1:8765
  - **Dev (hot reload):** Terminal A: `python scripts/serve_story_demo.py` — Terminal B: `cd frontend && npm run dev` → http://localhost:5173 (Vite proxies `/api` to :8765).
  - **GET `/api/health`** — reports RAG data readiness (PageIndex cache, IRC HTML, Tax Court JSONL). **POST `/api/plan`** returns **`narrative_report`** and **`retrieval_preview`**. Default is **live hybrid RAG**; check **“Stub retrieval only”** in the UI (or send `use_mock: true`) to use the offline stub.
  - Optional: set `NARRATIVE_LLM=1` and `OPENAI_API_KEY` to tighten prose via the LLM (see `src/planning/narrative_report.py`).
- Add other data-prep or indexing scripts here (e.g. tree builder, BM25 indexer) as the pipeline grows.
