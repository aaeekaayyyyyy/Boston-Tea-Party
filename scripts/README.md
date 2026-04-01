# Scripts — Boston Tea Party 2.0

- **`download_samples.py`**: Download one representative sample of each source type (IRC, IRS Pub, Tax Court) into `sources/`. Run from repo root: `python scripts/download_samples.py`.
  - If you get SSL certificate errors, ensure Python can verify HTTPS (e.g. on macOS run **Install Certificates.command** from your Python app, or use a venv with `certifi`). Alternatively, save the samples manually from the URLs in the script.
- A minimal IRC sample is provided at `sources/irc/26_usc_1_sample.html` for local testing and the PageIndex spike if live download fails.
- **`run_planning_demo.py`**: Planning agent demo. Default uses `HybridRetrievalClient` (`src/rag/`). Use `--mock` for the old stub retriever.
- **`pageindex_spike.py`**: One-off PageIndex tree generation spike (see `docs/pageindex_spike_report.md`).
- Add other data-prep or indexing scripts here (e.g. tree builder, BM25 indexer) as the pipeline grows.
