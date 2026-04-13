# Boston Tea Party 2.0

Welcome! **Boston Tea Party** is a hands-on learning lab for **tax-aware AI**: a small but real pipeline that combines **structured tax rules**, a **planning agent**, and **hybrid retrieval** over the Internal Revenue Code, IRS publication content, and Tax Court excerpts. If you have ever wondered how to keep an assistant **honest** (citations you can check, logic you can inspect), you are in the right place.

This is an **educational and research prototype**—not tax advice, not a substitute for a professional—but it is designed to make the *engineering* of grounded systems **concrete and fun to explore**.

---

## Why this project exists

Tax is a perfect stress test for retrieval-augmented systems:

- Answers should tie back to **real sources** (statute, publications, case snippets).
- **Tax year** and **document edition** matter—a fluent paragraph is not enough.
- Users rarely give every fact up front, so the system should **ask the right follow-up questions** before jumping to retrieval.

Boston Tea Party shows one pattern for doing that: **YAML rules** express constraints, a **planning agent** decides what to ask or what to retrieve, and a **hybrid retriever** returns passages with **rich metadata** (citations, sections, publication ids, case names, URLs when available) so you can verify what the UI is showing.

---

## What you get

| Piece | What it does |
|--------|----------------|
| **Constraint engine** | Evaluates taxpayer facts against rules in `src/rules/` (filing status, deductions, credits, documentation, and more). |
| **Planning agent** | Asks prioritized follow-ups when facts are missing; when ready, drives retrieval with rule-specific hints (e.g. which IRC sections or publication to lean on). |
| **Hybrid RAG** | **BM25** over three lanes: PageIndex-backed IRS publication tree (`data/rag/pageindex_irs_tree.json`), parsed IRC HTML (`sources/irc/`), and Tax Court JSONL (`data/rag/tax_court_corpus.jsonl`). |
| **Web demo** | **React** frontend + **FastAPI** backend: plan narrative, advisory panels, and a **retrieval preview** with citations. |
| **Evaluation** | Golden retrieval tests (`eval/rag_golden_test.py`) and additional eval scaffolding under `eval/` for deeper experiments. |

The contracts that glue retrieval to planning live in `src/planning/contracts.py`; the retrieval behavior is summarized in `src/rag/README.md` and `docs/retrieval_interface_spec.md`.

---

## Quick start

### 1. Python environment

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Data you already have vs. optional refresh

The repo is meant to run **out of the box** with the **cached** PageIndex tree and committed IRC HTML and Tax Court lines where included. If something is missing, the API health check will tell you.

- **Refresh IRS publication tree** (optional, needs an API key): see `scripts/refresh_pageindex_tree.py` and `data/rag/README.md`.
- **Download more IRC sections**: `python scripts/download_irc_sections.py`
- **Append Tax Court lines**: `python scripts/ingest_tax_court_line.py`

Full script index: **`scripts/README.md`**.

### 3. Run the full-stack demo

**Production-style** (API serves built React):

```bash
cd frontend && npm install && npm run build && cd ..
python scripts/serve_story_demo.py
```

Open **http://127.0.0.1:8765**. Interactive API docs: **http://127.0.0.1:8765/docs**.

**Development** (hot reload on the frontend):

- Terminal A: `python scripts/serve_story_demo.py`
- Terminal B: `cd frontend && npm run dev` → **http://localhost:5173** (Vite proxies `/api` to port 8765)

### 4. Try retrieval and planning from the CLI

```bash
python scripts/run_planning_demo.py              # hybrid RAG (default)
python scripts/run_planning_demo.py --mock      # stub retriever, no corpora needed
```

### 5. Run the golden retrieval suite

```bash
python eval/rag_golden_test.py
```

Expectations live in `data/rag/golden_retrieval.jsonl`. IRC cases **skip** automatically if the matching HTML file is not under `sources/irc/`.

---

## API cheat sheet

| Endpoint | Purpose |
|----------|---------|
| `GET /api/health` | RAG readiness (PageIndex cache, IRC files, Tax Court corpus). |
| `POST /api/plan` | Body: `{ "facts": { ... }, "use_mock": false }`. Returns planning outcome, `narrative_report`, and `retrieval_preview`. Set `use_mock: true` for offline stub retrieval. |

---

## Environment variables (optional)

Create a **`.env`** file in the repo root (do not commit secrets). Keys are loaded without overriding existing shell variables.

| Variable | Used for |
|----------|-----------|
| `PAGEINDEX_API_KEY` | Refreshing the IRS PageIndex tree via API. |
| `PAGEINDEX_IRS_DOC_ID` | Optional document id override for PageIndex. |
| `OPENAI_API_KEY` | Optional narrative tightening when enabled. |
| `NARRATIVE_LLM` | Set to `1` to enable optional LLM narrative path (see `src/planning/narrative_report.py`). |

---

## Repository map

```text
Boston-Tea-Party/
├── README.md                 ← you are here
├── requirements.txt
├── scripts/                  CLI tools, demo server (see scripts/README.md)
├── frontend/                 React + Vite UI
├── src/
│   ├── planning/             Agent, contracts, intake, narrative
│   ├── rag/                  Hybrid client, BM25, IRC parser, PageIndex bridge
│   └── rules/                YAML tax rules
├── eval/                     Golden tests, metrics, harnesses
├── data/rag/                 PageIndex cache, Tax Court JSONL, golden queries
├── sources/                  IRC HTML, samples (see sources/README.md)
└── docs/                     Specs, structure notes, spike reports
```

---

## Learning paths

1. **Start at the UI** — Enter facts, watch follow-up questions, then inspect **retrieval preview** citations.
2. **Read the contracts** — `src/planning/contracts.py` shows how chunks and metadata are shaped for verification.
3. **Trace one rule** — Pick a YAML file under `src/rules/` and see how the agent maps it to retrieval options in `src/planning/agent.py`.
4. **Break and fix retrieval** — Temporarily rename `data/rag/pageindex_irs_tree.json`, hit `GET /api/health`, and watch the system report what is missing.
5. **Extend the golden set** — Add a line to `data/rag/golden_retrieval.jsonl` and run `eval/rag_golden_test.py`.

---

## Disclaimer

This project is for **education and research**. Tax law depends on facts, timing, and jurisdiction. **It is not legal, tax, or financial advice.** Always consult a qualified professional for real filing decisions.

---

## Credits and docs

- **Script reference:** [scripts/README.md](scripts/README.md)
- **RAG internals:** [src/rag/README.md](src/rag/README.md)
- **Data layout:** [data/rag/README.md](data/rag/README.md), [sources/README.md](sources/README.md)
- **Retrieval interface:** [docs/retrieval_interface_spec.md](docs/retrieval_interface_spec.md)
- **Document structure notes:** [docs/structure_analysis.md](docs/structure_analysis.md)

If you are teaching or studying RAG, constraints, or human-in-the-loop fact gathering, we hope this repo gives you a **playground with guardrails**—and a reason to geek out about citations. Enjoy the deep dive.
