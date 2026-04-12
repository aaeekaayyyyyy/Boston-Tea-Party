"""
Tree-based vs flat BM25 retrieval comparison.

For each IRS Publication benchmark scenario, retrieves using the same
IRSPublicationRetriever path the prototype system uses, but with two
deterministic configurations:
  - Tree: current BM25 path with query augmentation, title/trail boost,
    and shallow-node penalty
  - Flat BM25: same retriever but text-only BM25 without structural boost

The optional IRS LLM reranker is disabled for both modes so this remains a
stable lexical retrieval comparison.

Usage:
    python -m eval.retrieval_comparison
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.loader import load_all_scenarios
from eval.metrics.retrieval_metrics import precision_at_k, mrr
from src.rag.irs_pageindex import IRSPublicationRetriever


def _search_citations(
    retriever: IRSPublicationRetriever,
    query: str,
    top_k: int,
    *,
    flat_bm25: bool,
) -> list[str]:
    """Run the IRS retriever in a deterministic comparison mode and return citations."""
    hits = retriever.search(
        query,
        top_k,
        options={
            "irs_flat_bm25": flat_bm25,
            "irs_llm_rerank": False,
            "irs_joint_refusal_augmentation": True,
        },
    )
    return [retriever.citation_for(row) for _score, row in hits]


def run_comparison(top_k: int = 5) -> dict:
    """Run tree vs flat BM25 on all IRS Pub scenarios."""
    all_scenarios = load_all_scenarios()
    baseline_types = {"factual_lookup", "eligibility_determination", "calculation", None}
    # Filter to answer-style IRS pub scenarios (exclude planning cases).
    irs_scenarios = [
        s for s in all_scenarios
        if s.get("source_type") == "irs_pubs" and s.get("question_type") in baseline_types
    ]
    print(f"Running retrieval comparison on {len(irs_scenarios)} IRS Pub scenarios")

    # Discover publications from scenario metadata.
    # NOTE: Currently all IRS Pub scenarios reference Pub 501.
    # This reads from data so it will generalize when new pubs are indexed.
    import re as _re
    pubs_seen = set()
    for s in irs_scenarios:
        for p in s.get("true_source_passages", []):
            m = _re.search(r"Pub\.?\s*(\d+)", p.get("citation", ""), _re.IGNORECASE)
            if m:
                pubs_seen.add(m.group(1))
    if not pubs_seen:
        pubs_seen = {"501"}
    print(f"  Publications referenced in benchmarks: {sorted(pubs_seen)}")

    # Build retriever. Single cache file for now; loop for future-proofing.
    retriever = None
    flat = []
    for pub_num in sorted(pubs_seen):
        cache = ROOT / "data" / "rag" / "pageindex_irs_tree.json"
        r = IRSPublicationRetriever(
            publication=pub_num,
            publication_year=2025,
            cache_path=cache,
        )
        nodes = r.ensure_flat()
        if nodes:
            flat = nodes
            retriever = r
            print(f"  Pub {pub_num}: {len(nodes)} flat nodes")

    if not flat or retriever is None:
        print("ERROR: No flat nodes available from PageIndex tree")
        return {}

    results = []
    for s in irs_scenarios:
        sid = s["id"]
        query = s["question"]
        gold = s.get("required_citations", [])
        if not gold:
            continue

        # Compare the real IRS retriever path in two deterministic modes.
        tree_citations = _search_citations(retriever, query, top_k, flat_bm25=False)
        flat_citations = _search_citations(retriever, query, top_k, flat_bm25=True)

        # Score both
        tree_p5 = precision_at_k(tree_citations, gold, top_k)
        tree_mrr = mrr(tree_citations, gold)
        flat_p5 = precision_at_k(flat_citations, gold, top_k)
        flat_mrr = mrr(flat_citations, gold)

        entry = {
            "id": sid,
            "gold_citations": gold,
            "tree": {
                "citations": tree_citations,
                "precision_at_5": tree_p5,
                "mrr": tree_mrr,
            },
            "flat_bm25": {
                "citations": flat_citations,
                "precision_at_5": flat_p5,
                "mrr": flat_mrr,
            },
        }
        results.append(entry)
        tree_win = "TREE" if tree_mrr > flat_mrr else ("TIE" if tree_mrr == flat_mrr else "FLAT")
        print(f"  {sid}: tree P@5={tree_p5:.2f} MRR={tree_mrr:.2f} | flat P@5={flat_p5:.2f} MRR={flat_mrr:.2f} [{tree_win}]")

    # Aggregate
    n = len(results)
    if n == 0:
        return {"error": "No scorable scenarios"}

    summary = {
        "n_scenarios": n,
        "tree_avg_precision_at_5": sum(r["tree"]["precision_at_5"] for r in results) / n,
        "tree_avg_mrr": sum(r["tree"]["mrr"] for r in results) / n,
        "flat_avg_precision_at_5": sum(r["flat_bm25"]["precision_at_5"] for r in results) / n,
        "flat_avg_mrr": sum(r["flat_bm25"]["mrr"] for r in results) / n,
        "tree_wins": sum(1 for r in results if r["tree"]["mrr"] > r["flat_bm25"]["mrr"]),
        "flat_wins": sum(1 for r in results if r["flat_bm25"]["mrr"] > r["tree"]["mrr"]),
        "ties": sum(1 for r in results if r["tree"]["mrr"] == r["flat_bm25"]["mrr"]),
        "comparison_mode": {
            "tree": "irs retriever with query augmentation + structural boost",
            "flat_bm25": "irs retriever with query augmentation + text-only BM25",
            "irs_llm_rerank": False,
        },
    }

    print(f"\n--- Summary ({n} scenarios) ---")
    print(f"  Tree  avg P@5={summary['tree_avg_precision_at_5']:.3f}  avg MRR={summary['tree_avg_mrr']:.3f}")
    print(f"  Flat  avg P@5={summary['flat_avg_precision_at_5']:.3f}  avg MRR={summary['flat_avg_mrr']:.3f}")
    print(f"  Wins: tree={summary['tree_wins']} flat={summary['flat_wins']} ties={summary['ties']}")

    return {"summary": summary, "scenarios": results}


def generate_figure(data: dict, out_dir: Path) -> None:
    """Generate the tree vs BM25 comparison figure."""
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    scenarios = data["scenarios"]
    summary = data["summary"]
    ids = [r["id"] for r in scenarios]
    n = len(ids)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, max(3, n * 0.4 + 1)))

    TREE_COLOR = "#2980b9"
    FLAT_COLOR = "#e67e22"

    y = np.arange(n)
    h = 0.35

    # Left: MRR comparison
    tree_mrrs = [r["tree"]["mrr"] for r in scenarios]
    flat_mrrs = [r["flat_bm25"]["mrr"] for r in scenarios]

    ax1.barh(y - h / 2, tree_mrrs, h, label="Tree (structural boost)", color=TREE_COLOR, edgecolor="white")
    ax1.barh(y + h / 2, flat_mrrs, h, label="Flat BM25 (no boost)", color=FLAT_COLOR, edgecolor="white")
    ax1.set_yticks(y)
    ax1.set_yticklabels(ids, fontsize=8)
    ax1.set_xlabel("MRR")
    ax1.set_title(f"Mean Reciprocal Rank\nTree avg={summary['tree_avg_mrr']:.3f}  Flat avg={summary['flat_avg_mrr']:.3f}")
    ax1.legend(fontsize=7, loc="lower right")
    ax1.set_xlim(0, 1.1)
    ax1.invert_yaxis()

    # Right: P@5 comparison
    tree_p5s = [r["tree"]["precision_at_5"] for r in scenarios]
    flat_p5s = [r["flat_bm25"]["precision_at_5"] for r in scenarios]

    ax2.barh(y - h / 2, tree_p5s, h, label="Tree (structural boost)", color=TREE_COLOR, edgecolor="white")
    ax2.barh(y + h / 2, flat_p5s, h, label="Flat BM25 (no boost)", color=FLAT_COLOR, edgecolor="white")
    ax2.set_yticks(y)
    ax2.set_yticklabels(ids, fontsize=8)
    ax2.set_xlabel("Precision@5")
    ax2.set_title(f"Precision@5\nTree avg={summary['tree_avg_precision_at_5']:.3f}  Flat avg={summary['flat_avg_precision_at_5']:.3f}")
    ax2.legend(fontsize=7, loc="lower right")
    ax2.set_xlim(0, max(max(tree_p5s + flat_p5s, default=0) + 0.1, 0.5))
    ax2.invert_yaxis()

    plt.suptitle("Tree-Based vs. Flat BM25 Retrieval (IRS Pub Scenarios)", fontsize=12, fontweight="bold", y=1.02)
    plt.tight_layout()
    out = out_dir / "fig_tree_vs_bm25.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"\nFigure saved to {out}")


def main():
    data = run_comparison(top_k=5)
    if not data or "error" in data:
        return

    # Save results
    out_dir = ROOT / "eval" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"retrieval_comparison_{ts}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"\nResults saved to {out_path}")

    # Generate figure
    fig_dir = ROOT / "eval" / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    generate_figure(data, fig_dir)


if __name__ == "__main__":
    main()
