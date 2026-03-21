#!/usr/bin/env python3
"""
PageIndex spike: run tree generation on one IRC or IRS Pub PDF sample.
- Requires: PAGEINDEX_API_KEY in env (get from https://dash.pageindex.ai/api-keys).
- Requires: A PDF in sources/irs_pubs/ or sources/irc/ (e.g. p501_sample.pdf from download_samples.py).
- If no PDF or key: prints what to do and writes a short spike report.

Run from repo root: python scripts/pageindex_spike.py
"""
import os
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCES = REPO_ROOT / "sources"
REPORT_PATH = REPO_ROOT / "docs" / "pageindex_spike_report.md"


def _load_dotenv():
    """Load .env from repo root if PAGEINDEX_API_KEY is not already set."""
    if os.environ.get("PAGEINDEX_API_KEY"):
        return
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def find_sample_pdf():
    """Find one PDF under sources/ for the spike."""
    for d in [SOURCES / "irs_pubs", SOURCES / "irc"]:
        if not d.exists():
            continue
        for f in d.glob("*.pdf"):
            return f
    return None


def run_spike():
    _load_dotenv()
    api_key = os.environ.get("PAGEINDEX_API_KEY", "").strip()
    pdf_path = find_sample_pdf()

    if not api_key or not pdf_path:
        report = []
        report.append("# PageIndex spike — setup\n")
        if not api_key:
            report.append("- Set `PAGEINDEX_API_KEY` (from https://dash.pageindex.ai/api-keys) to run the live spike.\n")
        if not pdf_path:
            report.append("- PageIndex **accepts PDF only**. No PDF found under `sources/irc/` or `sources/irs_pubs/`.\n")
            report.append("  - Run `python scripts/download_samples.py` (fix SSL if needed) to fetch an IRS Pub PDF, or place any IRC/IRS Pub PDF there.\n")
        report.append("\n## Conclusion (without live run)\n")
        report.append("- **Tax-specific parsing**: For IRC we need **section/subsection metadata** (e.g. 26 USC § 1(c)) in retrieval results for citations. PageIndex tree nodes use `title`, `node_id`, `page_index`, `text`. We should map node titles or add a post-step to attach IRC/IRS section numbers from our structure analysis.\n")
        report.append("- **Recommendation**: Use PageIndex for tree generation and navigation; add a thin **tax-specific layer** that (1) parses our source types (IRC vs IRS Pub) and (2) enriches node metadata with section/publication/year for the verification layer.\n")
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text("".join(report), encoding="utf-8")
        print("No API key or PDF found. Wrote", REPORT_PATH)
        return

    try:
        from pageindex import PageIndexClient
    except ImportError:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(
            "# PageIndex spike — install\nInstall with: `pip install pageindex`\n",
            encoding="utf-8",
        )
        print("Install pageindex: pip install pageindex")
        return

    client = PageIndexClient(api_key=api_key)
    doc_id = client.submit_document(str(pdf_path))["doc_id"]
    print("Submitted", pdf_path.name, "-> doc_id:", doc_id)

    # Poll for completion (simple: a few tries)
    import time
    for _ in range(30):
        if client.is_retrieval_ready(doc_id):
            break
        time.sleep(2)

    if not client.is_retrieval_ready(doc_id):
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(
            f"# PageIndex spike — processing\nDocument {doc_id} still processing. Re-run later or check dashboard.\n",
            encoding="utf-8",
        )
        print("Still processing. Re-run later.")
        return

    tree = client.get_tree(doc_id, node_summary=True)
    result = tree.get("result") or []
    summary = []
    def collect_nodes(nodes, depth=0):
        for n in nodes:
            summary.append({"depth": depth, "title": n.get("title"), "node_id": n.get("node_id"), "page_index": n.get("page_index")})
            if n.get("nodes"):
                collect_nodes(n["nodes"], depth + 1)
    collect_nodes(result)

    report = []
    report.append("# PageIndex spike — result\n\n")
    report.append(f"**File**: `{pdf_path.name}`  \n**doc_id**: `{doc_id}`\n\n")
    report.append("## Tree shape (first 20 nodes)\n\n")
    for s in summary[:20]:
        report.append(f"- {'  ' * s['depth']} [{s['node_id']}] p.{s.get('page_index')} — {s.get('title', '')}\n")
    report.append("\n## Tax-specific parsing\n\n")
    report.append("- PageIndex returns a clean hierarchy (title, node_id, page_index, text). For **IRC/IRS Pubs** we still need to attach **section numbers and publication year** for citations (see `docs/structure_analysis.md`).\n")
    report.append("- **Recommendation**: Use PageIndex for tree build and LLM-based navigation; add a **tax metadata layer** that maps nodes back to IRC § or IRS Pub section from our parser.\n")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("".join(report), encoding="utf-8")
    print("Wrote", REPORT_PATH)


if __name__ == "__main__":
    run_spike()
