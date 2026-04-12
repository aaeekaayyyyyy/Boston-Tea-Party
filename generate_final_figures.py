"""
Boston Tea Party 2.0 -- Final Presentation Figures

Presentation workflow:
1. Archive old files out of eval/results so the folder contains only the current rerun batch.
2. Rerun the desired stochastic eval commands multiple times.
3. Run this script to generate figures from the current batch.

Selection rules:
- Stochastic tracks use fresh-run averages across all matching files currently in eval/results:
  - baseline eval: eval_*.json with baseline summaries
  - prompted prototype eval: eval_*.json with system summaries
  - planning-system eval: planning_eval_*.json
- Deterministic benchmarks use the latest file only:
  - constraint_*.json
  - retrieval_verification_*.json
  - retrieval_comparison_*.json
"""
from __future__ import annotations

import csv
import glob
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
try:
    import pandas as pd
except ImportError:
    pd = None
import seaborn as sns
from matplotlib.lines import Line2D


REPO = Path(__file__).resolve().parent
RESULTS = REPO / "eval" / "results"
FIGURES = REPO / "eval" / "figures"
FIGURES.mkdir(parents=True, exist_ok=True)

sns.set_theme(style="whitegrid", palette="muted")
plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "font.family": "sans-serif",
    "font.size": 10,
    "axes.titlesize": 12,
    "axes.titleweight": "bold",
    "axes.labelsize": 10,
    "axes.edgecolor": "#cccccc",
    "grid.color": "#eeeeee",
})

PASS_COLOR = "#27ae60"
FAIL_COLOR = "#c0392b"
BLUE = "#2980b9"
ORANGE = "#d35400"
TARGET_COLOR = "#333333"
GRAY = "#95a5a6"
LIGHT_BLUE = "#7fb3d5"


def _load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_eval_runs() -> tuple[list[dict], list[dict]]:
    files = sorted(glob.glob(str(RESULTS / "eval_*.json")))
    baselines, systems = [], []
    for f in files:
        d = _load_json(f)
        summary = d.get("summary", {})
        if "system_accuracy" in summary:
            systems.append(d)
        elif "baseline_a_accuracy" in summary:
            baselines.append(d)
    return baselines, systems


def load_planning_runs() -> list[dict]:
    return [_load_json(f) for f in sorted(glob.glob(str(RESULTS / "planning_eval_*.json")))]


def _load_latest(pattern: str) -> dict | None:
    files = sorted(glob.glob(str(RESULTS / pattern)))
    if not files:
        return None
    return _load_json(files[-1])


def load_constraint() -> dict | None:
    return _load_latest("constraint_*.json")


def load_retrieval_verification() -> dict | None:
    return _load_latest("retrieval_verification_*.json")


def load_retrieval_comparison() -> dict | None:
    return _load_latest("retrieval_comparison_*.json")


def get_vals(runs: list[dict], key: str) -> list[float]:
    return [float(r["summary"][key]) for r in runs if key in r.get("summary", {})]


def mean_or_none(values: list[float]) -> float | None:
    if not values:
        return None
    return float(np.mean(values))


def std_or_zero(values: list[float]) -> float:
    if len(values) <= 1:
        return 0.0
    return float(np.std(values))


def write_table_artifact(filename_stem: str, columns: list[str], rows: list[list[str]]) -> None:
    csv_path = FIGURES / f"{filename_stem}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        writer.writerows(rows)
    print(f"  {csv_path.name}")

    html_path = FIGURES / f"{filename_stem}.html"
    if pd is not None:
        df = pd.DataFrame(rows, columns=columns)
        html_path.write_text(df.to_html(index=False), encoding="utf-8")
    else:
        header = "".join(f"<th>{col}</th>" for col in columns)
        body = "".join(
            "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
            for row in rows
        )
        html = (
            "<html><head><meta charset='utf-8'><title>Scorecard</title></head>"
            "<body><table border='1' cellspacing='0' cellpadding='6'>"
            f"<thead><tr>{header}</tr></thead><tbody>{body}</tbody></table>"
            "</body></html>"
        )
        html_path.write_text(html, encoding="utf-8")
    print(f"  {html_path.name}")


def _scenario_track_aggregate(runs: list[dict], track_key: str) -> list[dict]:
    if not runs:
        return []
    first_order = [s["id"] for s in runs[0].get("scenarios", [])]
    by_run = []
    for run in runs:
        by_run.append({s["id"]: (s.get(track_key) or {}) for s in run.get("scenarios", [])})

    aggregated = []
    for sid in first_order:
        entries = [mapping.get(sid, {}) for mapping in by_run]
        aggregated.append(
            {
                "id": sid,
                "entries": entries,
                "hallucination_truncated": any(e.get("hallucination_truncated") for e in entries),
            }
        )
    return aggregated


def _mean_entry(entries: list[dict], getter) -> float:
    vals = []
    for entry in entries:
        value = getter(entry)
        if value is None:
            continue
        try:
            if np.isnan(value):
                continue
        except TypeError:
            pass
        vals.append(float(value))
    return float(np.mean(vals)) if vals else np.nan


def _fraction_true(entries: list[dict], key: str) -> float:
    vals = [1.0 if e.get(key) else 0.0 for e in entries if key in e]
    return float(np.mean(vals)) if vals else np.nan


def fig_tree_vs_bm25(data: dict | None) -> None:
    if not data:
        print("  fig_tree_vs_bm25: skipped (no retrieval comparison data)")
        return

    scenarios = data["scenarios"]
    summary = data["summary"]
    ids = [r["id"] for r in scenarios]
    n = len(ids)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, max(3, n * 0.4 + 1)))
    y = np.arange(n)
    h = 0.35

    tree_mrrs = [r["tree"]["mrr"] for r in scenarios]
    flat_mrrs = [r["flat_bm25"]["mrr"] for r in scenarios]
    ax1.barh(y - h / 2, tree_mrrs, h, label="Tree (structural boost)", color=BLUE, edgecolor="white")
    ax1.barh(y + h / 2, flat_mrrs, h, label="Flat BM25 (no boost)", color=ORANGE, edgecolor="white")
    ax1.set_yticks(y)
    ax1.set_yticklabels(ids, fontsize=8)
    ax1.set_xlabel("MRR")
    ax1.set_title(
        f"Mean Reciprocal Rank\nTree avg={summary['tree_avg_mrr']:.3f}  Flat avg={summary['flat_avg_mrr']:.3f}"
    )
    ax1.legend(fontsize=7, loc="lower right")
    ax1.set_xlim(0, 1.1)
    ax1.invert_yaxis()

    tree_p5s = [r["tree"]["precision_at_5"] for r in scenarios]
    flat_p5s = [r["flat_bm25"]["precision_at_5"] for r in scenarios]
    ax2.barh(y - h / 2, tree_p5s, h, label="Tree (structural boost)", color=BLUE, edgecolor="white")
    ax2.barh(y + h / 2, flat_p5s, h, label="Flat BM25 (no boost)", color=ORANGE, edgecolor="white")
    ax2.set_yticks(y)
    ax2.set_yticklabels(ids, fontsize=8)
    ax2.set_xlabel("Precision@5")
    ax2.set_title(
        f"Precision@5\nTree avg={summary['tree_avg_precision_at_5']:.3f}  Flat avg={summary['flat_avg_precision_at_5']:.3f}"
    )
    ax2.legend(fontsize=7, loc="lower right")
    ax2.set_xlim(0, max(max(tree_p5s + flat_p5s, default=0) + 0.1, 0.5))
    ax2.invert_yaxis()

    plt.suptitle("Tree-Based vs. Flat BM25 Retrieval (IRS Pub Scenarios)", fontsize=12, fontweight="bold", y=1.02)
    plt.tight_layout()
    out = FIGURES / "fig_tree_vs_bm25.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  {out.name}")


def fig1_baselines(runs: list[dict]) -> None:
    n = len(runs)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 3.5), gridspec_kw={"width_ratios": [1, 2]})

    a_vals = get_vals(runs, "baseline_a_accuracy")
    b_vals = get_vals(runs, "baseline_b_accuracy")
    cats = ["Baseline A\n(zero-shot)", "Baseline B\n(gold sources)"]
    means = [np.mean(a_vals), np.mean(b_vals)]
    stds = [std_or_zero(a_vals), std_or_zero(b_vals)]

    bars = ax1.bar(cats, means, yerr=stds, color=[BLUE, ORANGE], width=0.5,
                   edgecolor="white", linewidth=0.8, zorder=3, capsize=4,
                   error_kw={"linewidth": 1.2, "color": "#333"})
    ax1.axhline(y=0.80, color=TARGET_COLOR, linewidth=1.2, linestyle="--", zorder=2)
    for bar, mean, std in zip(bars, means, stds):
        label = f"{mean:.1%}" if std < 0.001 else f"{mean:.1%} +/- {std:.1%}"
        ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + std + 0.025,
                 label, ha="center", va="bottom", fontsize=8, fontweight="bold")
    ax1.set_ylim(0, 1.15)
    ax1.set_ylabel("Accuracy")
    ax1.set_title(f"Answer Correctness (n={n} runs)")
    ax1.tick_params(labelsize=8)

    metric_defs = [
        ("baseline_b_avg_faithfulness", "Faithfulness", 0.85, "higher"),
        ("baseline_b_avg_hallucination_rate", "Hallucination\nRate", 0.10, "lower"),
        ("baseline_b_avg_citation_existence", "Citation\nExistence", 0.90, "higher"),
        ("baseline_b_avg_citation_f1", "Citation F1", 0.90, "higher"),
    ]
    names = [label for _, label, _, _ in metric_defs]
    means = [mean_or_none(get_vals(runs, key)) for key, *_ in metric_defs]
    stds = [std_or_zero(get_vals(runs, key)) for key, *_ in metric_defs]
    targets = [target for _, _, target, _ in metric_defs]
    directions = [direction for _, _, _, direction in metric_defs]
    x = np.arange(len(names))
    bars2 = ax2.bar(x, means, yerr=stds, color=ORANGE, width=0.55,
                    edgecolor="white", linewidth=0.8, zorder=3, capsize=4,
                    error_kw={"linewidth": 1.2, "color": "#333"})
    for i, target in enumerate(targets):
        ax2.plot([i - 0.35, i + 0.35], [target, target], color=TARGET_COLOR,
                 linewidth=1.5, linestyle="--", zorder=4)
    for bar, mean, std in zip(bars2, means, stds):
        label = f"{mean:.3f}" if std < 0.001 else f"{mean:.2f}+/-{std:.2f}"
        ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + std + 0.025,
                 label, ha="center", va="bottom", fontsize=7.5, fontweight="bold")
    ax2.set_xticks(x)
    ax2.set_xticklabels(names, fontsize=8)
    ax2.set_ylim(0, 1.2)
    ax2.set_ylabel("Score")
    ax2.set_title(f"Baseline B Quality Metrics (n={n} runs)")
    ax2.legend(handles=[Line2D([0], [0], color=TARGET_COLOR, linewidth=1.5, linestyle="--", label="Target threshold")],
               fontsize=7, loc="upper right", framealpha=0.9)

    plt.tight_layout()
    out = FIGURES / "fig1_baselines.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  {out.name}")


def fig2_heatmap(runs: list[dict]) -> None:
    aggregated = _scenario_track_aggregate(runs, "baseline_b")
    ids = [row["id"] for row in aggregated]
    metric_specs = [
        ("Answer\nCorrect", lambda entries: _fraction_true(entries, "answer_correct")),
        ("Halluc.\nSafety", lambda entries: _mean_entry(entries, lambda data: 1.0 - data["hallucination_rate"] if "hallucination_rate" in data else None)),
        ("Faithful.", lambda entries: _mean_entry(entries, lambda data: data.get("faithfulness") if "faithfulness" in data else None)),
        ("Cite Exist.", lambda entries: _mean_entry(entries, lambda data: data.get("citation_existence") if "citation_existence" in data else None)),
        ("Cite F1", lambda entries: _mean_entry(entries, lambda data: data.get("citation_f1") if "citation_f1" in data else None)),
    ]

    matrix = [[getter(row["entries"]) for _, getter in metric_specs] for row in aggregated]
    data = np.array(matrix, dtype=float)
    keep_cols = [i for i in range(data.shape[1]) if not np.isnan(data[:, i]).all()]
    data = data[:, keep_cols]
    metric_names = [metric_specs[i][0] for i in keep_cols]
    table_rows = []
    for sid, row_vals in zip(ids, data):
        formatted = ["" if np.isnan(v) else f"{v:.3f}" for v in row_vals]
        table_rows.append([sid, *formatted])
    write_table_artifact("baseline_b_heatmap", ["Scenario", *metric_names], table_rows)

    fig, ax = plt.subplots(figsize=(6, max(4, len(ids) * 0.45)))
    sns.heatmap(data, annot=True, fmt=".2f", cmap="RdYlGn", vmin=0, vmax=1,
                mask=np.isnan(data),
                xticklabels=metric_names, yticklabels=ids,
                linewidths=0.5, linecolor="#ddd", cbar_kws={"label": "Score"}, ax=ax)
    ax.set_title(f"Per-Scenario Baseline B Scores (n={len(runs)} runs)", pad=12)
    ax.set_ylabel("")
    ax.tick_params(axis="y", labelsize=8)
    ax.tick_params(axis="x", labelsize=9)

    plt.tight_layout()
    out = FIGURES / "fig2_heatmap.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  {out.name}")


def fig3_constraints(constraint_data: dict | None) -> None:
    if not constraint_data:
        print("  fig3: skipped (no constraint data)")
        return

    domains = constraint_data["summary"]["per_domain"]
    names = [d.replace("_", " ").title() for d in domains]
    passed = [domains[d]["passed"] for d in domains]
    total = [domains[d]["cases"] for d in domains]
    f1s = [domains[d]["f1"] for d in domains]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 3.5), gridspec_kw={"width_ratios": [1.2, 1]})
    y = np.arange(len(names))
    failed = [t - p for p, t in zip(passed, total)]
    ax1.barh(y, passed, color=BLUE, label="Passed", edgecolor="white", linewidth=0.5, height=0.55)
    ax1.barh(y, failed, left=passed, color=GRAY, label="Failed", edgecolor="white", linewidth=0.5, height=0.55)
    for i, (p, t) in enumerate(zip(passed, total)):
        ax1.text(t + 0.3, i, f"{p}/{t}", va="center", fontsize=9, fontweight="bold")
    ax1.set_yticks(y)
    ax1.set_yticklabels(names, fontsize=9)
    ax1.set_xlabel("Cases")
    ax1.set_title("Pass Rate by Domain")
    ax1.legend(loc="lower right", fontsize=8)
    ax1.set_xlim(0, max(total) + 2)
    ax1.invert_yaxis()

    ax2.barh(y, f1s, color=BLUE, edgecolor="white", linewidth=0.5, height=0.55)
    ax2.axvline(x=0.90, color=TARGET_COLOR, linewidth=2, linestyle="--", zorder=4)
    for i, f in enumerate(f1s):
        ax2.text(f + 0.01, i, f"{f:.3f}", va="center", fontsize=9, fontweight="bold")
    ax2.set_yticks(y)
    ax2.set_yticklabels(names, fontsize=9)
    ax2.set_xlabel("F1 Score")
    ax2.set_title("Element-Level F1 by Domain")
    ax2.set_xlim(0, 1.12)
    ax2.legend(handles=[Line2D([0], [0], color=TARGET_COLOR, linewidth=2, linestyle="--", label="Target (0.90)")],
               loc="lower right", fontsize=8)
    ax2.invert_yaxis()

    s = constraint_data["summary"]
    plt.suptitle(
        f"Constraint Engine: {s['cases_passed']}/{s['n_cases']} cases, F1 = {s['f1']:.3f}",
        fontsize=12, fontweight="bold", y=1.02,
    )
    plt.tight_layout()
    out = FIGURES / "fig3_constraints.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  {out.name}")


def fig4_retrieval(rv_data: dict | None) -> None:
    if not rv_data:
        print("  fig4: skipped (no retrieval verification data)")
        return

    s = rv_data["summary"]
    checks = []
    golden = s.get("golden_retrieval")
    if golden:
        checks.append(("Golden\nRetrieval", golden.get("passed", 0), golden.get("total", 0)))
    checks.extend([
        ("Source-Type\nConsistency", s["source_type_consistency"]["passed"], s["source_type_consistency"]["applicable"]),
        ("Tax-Year\nValidation", s["tax_year_validation"]["passed"], s["tax_year_validation"]["applicable"]),
        ("Provenance\nCompleteness", s["provenance_completeness"]["all_complete"], s["provenance_completeness"]["applicable"]),
    ])

    fig, ax = plt.subplots(figsize=(6, 3))
    names = [c[0] for c in checks]
    passed_vals = [c[1] for c in checks]
    total_vals = [c[2] for c in checks]
    rates = [p / t if t > 0 else 0 for p, t in zip(passed_vals, total_vals)]

    x = np.arange(len(names))
    bars = ax.bar(x, rates, color=BLUE, width=0.52, edgecolor="white", linewidth=0.8, zorder=3)
    for bar, p, t in zip(bars, passed_vals, total_vals):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.025,
                f"{p}/{t}", ha="center", va="bottom", fontsize=10, fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(names, fontsize=9)
    ax.set_ylim(0, 1.15)
    ax.set_ylabel("Pass Rate")
    ax.set_title("Retrieval Quality Checks (latest measured results)", pad=10)

    plt.tight_layout()
    out = FIGURES / "fig4_retrieval.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  {out.name}")


def fig5_hallucination(baseline_runs: list[dict], system_runs: list[dict]) -> None:
    base_rows = _scenario_track_aggregate(baseline_runs, "baseline_b")
    sys_rows = {row["id"]: row for row in _scenario_track_aggregate(system_runs, "system")}

    hal_data = []
    for row in base_rows:
        sid = row["id"]
        sys_row = sys_rows.get(sid)
        base_rate = _mean_entry(row["entries"], lambda data: data.get("hallucination_rate") if "hallucination_rate" in data else None)
        sys_rate = np.nan
        truncated = False
        if sys_row:
            sys_rate = _mean_entry(sys_row["entries"], lambda data: data.get("hallucination_rate") if "hallucination_rate" in data else None)
            truncated = sys_row["hallucination_truncated"]
        if np.isnan(base_rate) and np.isnan(sys_rate):
            continue
        hal_data.append({
            "id": sid + ("*" if truncated else ""),
            "base_rate": base_rate,
            "sys_rate": sys_rate,
            "max_rate": np.nanmax([base_rate, sys_rate]),
        })

    hal_data.sort(key=lambda x: x["max_rate"], reverse=True)
    if not hal_data:
        print("  fig5: skipped (no hallucination data)")
        return

    fig, ax = plt.subplots(figsize=(10, max(3, len(hal_data) * 0.45)))
    y = np.arange(len(hal_data))
    h = 0.34
    base_vals = [x["base_rate"] for x in hal_data]
    sys_vals = [x["sys_rate"] for x in hal_data]
    ax.barh(y - h / 2, base_vals, height=h, color=ORANGE, edgecolor="white", linewidth=0.5, label="Baseline B")
    if system_runs:
        ax.barh(y + h / 2, np.nan_to_num(sys_vals, nan=0.0), height=h, color=BLUE, edgecolor="white", linewidth=0.5, label="System")

    ax.axvline(x=0.10, color=TARGET_COLOR, linewidth=2, linestyle="--", zorder=4)
    for i, row in enumerate(hal_data):
        if not np.isnan(row["base_rate"]):
            ax.text(row["base_rate"] + 0.005, i - h / 2, f"{row['base_rate']:.3f}", va="center", fontsize=8, color="#555")
        if system_runs and not np.isnan(row["sys_rate"]):
            suffix = "*" if row["id"].endswith("*") else ""
            ax.text(row["sys_rate"] + 0.005, i + h / 2, f"{row['sys_rate']:.3f}{suffix}", va="center", fontsize=8, color="#555")

    ax.set_yticks(y)
    ax.set_yticklabels([hdata["id"] for hdata in hal_data], fontsize=8)
    ax.set_xlabel("Hallucination Rate")
    title = f"LettuceDetect Hallucination Rate by Scenario (n={len(baseline_runs)} baseline runs"
    if system_runs:
        title += f", n={len(system_runs)} system runs)\n* system hallucination scored on truncated context"
    else:
        title += ")"
    ax.set_title(title)
    ax.legend(handles=[
        mpatches.Patch(facecolor=ORANGE, label="Baseline B"),
        mpatches.Patch(facecolor=BLUE, label="System"),
        Line2D([0], [0], color=TARGET_COLOR, linewidth=2, linestyle="--", label="Target (0.10)"),
    ] if system_runs else [
        Line2D([0], [0], color=TARGET_COLOR, linewidth=2, linestyle="--", label="Target (0.10)"),
    ], loc="lower right", fontsize=8)
    ax.invert_yaxis()
    ax.set_xlim(0, max(hdata["max_rate"] for hdata in hal_data) + 0.08)

    plt.tight_layout()
    out = FIGURES / "fig5_hallucination.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  {out.name}")


def fig6_system_comparison(baseline_runs: list[dict], system_runs: list[dict]) -> None:
    if not system_runs:
        print("  fig6: skipped (no system results)")
        return

    metric_specs = [
        ("Answer\nCorrectness", mean_or_none(get_vals(baseline_runs, "baseline_b_accuracy")), mean_or_none(get_vals(system_runs, "system_accuracy")), 0.80),
        ("Faithfulness", mean_or_none(get_vals(baseline_runs, "baseline_b_avg_faithfulness")), mean_or_none(get_vals(system_runs, "system_avg_faithfulness")), 0.85),
        ("Hallucination\nRate", mean_or_none(get_vals(baseline_runs, "baseline_b_avg_hallucination_rate")), mean_or_none(get_vals(system_runs, "system_avg_hallucination_rate")), 0.10),
        ("Citation\nExistence", mean_or_none(get_vals(baseline_runs, "baseline_b_avg_citation_existence")), mean_or_none(get_vals(system_runs, "system_avg_citation_existence")), 0.90),
        ("Citation F1", mean_or_none(get_vals(baseline_runs, "baseline_b_avg_citation_f1")), mean_or_none(get_vals(system_runs, "system_avg_citation_f1")), 0.90),
    ]
    available = [(label, b_val, s_val, target) for label, b_val, s_val, target in metric_specs if b_val is not None and s_val is not None]
    if not available:
        print("  fig6: skipped (no overlapping system metrics)")
        return

    metrics = [label for label, *_ in available]
    b_means = [b for _, b, _, _ in available]
    s_means = [s for _, _, s, _ in available]
    targets = [t for _, _, _, t in available]

    fig, ax = plt.subplots(figsize=(10, 4.5))
    x = np.arange(len(metrics))
    w = 0.32
    ax.bar(x - w / 2, b_means, w, label="Baseline B (gold sources)", color=ORANGE, edgecolor="white", linewidth=0.8, zorder=3)
    ax.bar(x + w / 2, s_means, w, label="Prompted RAG Prototype", color=BLUE, edgecolor="white", linewidth=0.8, zorder=3)

    for i, target in enumerate(targets):
        ax.plot([i - 0.4, i + 0.4], [target, target], color=TARGET_COLOR, linewidth=1.2, linestyle="--", zorder=2)

    for i, (b_val, s_val) in enumerate(zip(b_means, s_means)):
        ax.text(i - w / 2, b_val + 0.02, f"{b_val:.2f}", ha="center", va="bottom", fontsize=7.5, fontweight="bold", color="#555")
        ax.text(i + w / 2, s_val + 0.02, f"{s_val:.2f}", ha="center", va="bottom", fontsize=7.5, fontweight="bold", color="#555")

    ax.set_xticks(x)
    ax.set_xticklabels(metrics, fontsize=9)
    ax.set_ylim(0, 1.2)
    ax.set_ylabel("Metric value")
    ax.set_title(
        f"Prompted RAG Prototype vs. Baseline B\n(current batch: {len(baseline_runs)} baseline runs, {len(system_runs)} system runs)",
        pad=10,
    )
    ax.legend(fontsize=8, loc="upper left")

    plt.tight_layout()
    out = FIGURES / "fig6_system_vs_baseline.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  {out.name}")


def fig7_system_heatmap(system_runs: list[dict]) -> None:
    if not system_runs:
        print("  fig7: skipped (no system results)")
        return

    aggregated = _scenario_track_aggregate(system_runs, "system")
    ids = [row["id"] + ("*" if row["hallucination_truncated"] else "") for row in aggregated]
    metric_specs = [
        ("Answer\nCorrect", lambda entries: _fraction_true(entries, "answer_correct")),
        ("Halluc.\nSafety", lambda entries: _mean_entry(entries, lambda data: 1.0 - data["hallucination_rate"] if "hallucination_rate" in data else None)),
        ("Faithful.", lambda entries: _mean_entry(entries, lambda data: data.get("faithfulness") if "faithfulness" in data else None)),
        ("Cite Exist.", lambda entries: _mean_entry(entries, lambda data: data.get("citation_existence") if "citation_existence" in data else None)),
        ("Cite F1", lambda entries: _mean_entry(entries, lambda data: data.get("citation_f1") if "citation_f1" in data else None)),
    ]

    matrix = [[getter(row["entries"]) for _, getter in metric_specs] for row in aggregated]
    data = np.array(matrix, dtype=float)
    keep_cols = [i for i in range(data.shape[1]) if not np.isnan(data[:, i]).all()]
    data = data[:, keep_cols]
    metric_names = [metric_specs[i][0] for i in keep_cols]
    table_rows = []
    for sid, row_vals in zip(ids, data):
        formatted = ["" if np.isnan(v) else f"{v:.3f}" for v in row_vals]
        table_rows.append([sid, *formatted])
    write_table_artifact("prototype_heatmap", ["Scenario", *metric_names], table_rows)

    fig, ax = plt.subplots(figsize=(6, max(4, len(ids) * 0.45)))
    sns.heatmap(data, annot=True, fmt=".2f", cmap="RdYlGn", vmin=0, vmax=1,
                mask=np.isnan(data),
                xticklabels=metric_names, yticklabels=ids,
                linewidths=0.5, linecolor="#ddd", cbar_kws={"label": "Score"}, ax=ax)
    ax.set_title(f"Per-Scenario Prototype Scores (n={len(system_runs)} runs)\n* hallucination scored on truncated context", pad=12)
    ax.set_ylabel("")
    ax.tick_params(axis="y", labelsize=8)
    ax.tick_params(axis="x", labelsize=9)

    plt.tight_layout()
    out = FIGURES / "fig7_system_heatmap.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  {out.name}")


def fig8_scorecard(baseline_runs: list[dict], system_runs: list[dict], constraint_data: dict | None, rv_data: dict | None) -> None:
    rows = []

    if rv_data:
        s = rv_data["summary"]
        golden = s.get("golden_retrieval")
        if golden:
            gp, gt = golden.get("passed", 0), golden.get("total", 0)
            rows.append(("Golden Retrieval Quality", f"{gp}/{gt}", f"{gp/gt:.0%}" if gt else "N/A", gp == gt if gt else False))
        sc = s["source_type_consistency"]
        rows.append(("Source-Type Consistency", f"{sc['passed']}/{sc['applicable']}", f"{sc['passed']/sc['applicable']:.0%}" if sc['applicable'] else "N/A", sc["passed"] == sc["applicable"]))
        ty = s["tax_year_validation"]
        rows.append(("Tax-Year Validation", f"{ty['passed']}/{ty['applicable']}", f"{ty['passed']/ty['applicable']:.0%}" if ty['applicable'] else "N/A", ty["passed"] == ty["applicable"]))
        pc = s["provenance_completeness"]
        rows.append(("Provenance Completeness", f"{pc['all_complete']}/{pc['applicable']}", f"{pc['all_complete']/pc['applicable']:.0%}" if pc['applicable'] else "N/A", pc["all_complete"] == pc["applicable"]))

    if constraint_data:
        cs = constraint_data["summary"]
        rows.append(("Constraint Engine F1", f"{cs['cases_passed']}/{cs['n_cases']}", f"{cs['f1']:.3f}", cs["f1"] >= 0.90))

    if baseline_runs:
        b_acc = mean_or_none(get_vals(baseline_runs, "baseline_b_accuracy"))
        faith = mean_or_none(get_vals(baseline_runs, "baseline_b_avg_faithfulness"))
        hal = mean_or_none(get_vals(baseline_runs, "baseline_b_avg_hallucination_rate"))
        if b_acc is not None:
            rows.append(("Baseline B Accuracy", f"{len(baseline_runs)} runs", f"{b_acc:.1%}", b_acc >= 0.80))
        if faith is not None:
            rows.append(("Baseline B Faithfulness", f"{len(baseline_runs)} runs", f"{faith:.3f}", faith >= 0.85))
        if hal is not None:
            rows.append(("Baseline B Halluc. Safety", f"{len(baseline_runs)} runs", f"{1.0 - hal:.3f}", (1.0 - hal) >= 0.90))

    if system_runs:
        sa = mean_or_none(get_vals(system_runs, "system_accuracy"))
        sf = mean_or_none(get_vals(system_runs, "system_avg_faithfulness"))
        sh = mean_or_none(get_vals(system_runs, "system_avg_hallucination_rate"))
        sce = mean_or_none(get_vals(system_runs, "system_avg_citation_existence"))
        scf = mean_or_none(get_vals(system_runs, "system_avg_citation_f1"))
        ssce = mean_or_none(get_vals(system_runs, "system_avg_source_citation_existence"))
        if sa is not None:
            rows.append(("Prompted RAG Prototype Accuracy", f"{len(system_runs)} runs", f"{sa:.1%}", sa >= 0.80))
        if sf is not None:
            rows.append(("Prompted RAG Prototype Faithfulness", f"{len(system_runs)} runs", f"{sf:.3f}", sf >= 0.85))
        if sh is not None:
            rows.append(("Prompted RAG Prototype Halluc. Safety", f"{len(system_runs)} runs", f"{1.0 - sh:.3f}", (1.0 - sh) >= 0.90))
        if sce is not None:
            rows.append(("Prompted RAG Prototype Cite Exist. (section)", f"{len(system_runs)} runs", f"{sce:.3f}", sce >= 0.90))
        if scf is not None:
            rows.append(("Prompted RAG Prototype Citation F1", f"{len(system_runs)} runs", f"{scf:.3f}", scf >= 0.90))
        if ssce is not None:
            rows.append(("Prompted RAG Prototype Cite Exist. (source)", f"{len(system_runs)} runs", f"{ssce:.3f}", False))

    if not rows:
        print("  fig8: skipped (no data)")
        return

    fig, ax = plt.subplots(figsize=(8.8, max(3, len(rows) * 0.4 + 1)))
    ax.axis("off")
    col_labels = ["Metric", "Cases", "Score", "Status"]
    cell_text, cell_colors = [], []
    for name, cases, score, is_pass in rows:
        status = "PASS" if is_pass else "BELOW TARGET"
        cell_text.append([name, cases, score, status])
        cell_colors.append(["#f8fbff", "#f8fbff", "#f8fbff", "#eef4fb"])

    write_table_artifact("evaluation_scorecard", col_labels, cell_text)

    table = ax.table(cellText=cell_text, colLabels=col_labels, cellColours=cell_colors, loc="center", cellLoc="center")
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1.0, 1.4)
    for (row, _col), cell in table.get_celld().items():
        if row == 0:
            cell.set_facecolor("#2c3e50")
            cell.set_text_props(color="white", fontweight="bold")
        cell.set_edgecolor("#ddd")

    ax.set_title("Evaluation Scorecard (current batch)", fontsize=13, fontweight="bold", pad=15)
    plt.tight_layout()
    out = FIGURES / "fig8_scorecard.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  {out.name}")


def fig9_system_actuals(system_runs: list[dict]) -> None:
    if not system_runs:
        print("  fig9: skipped (no system results)")
        return

    accuracy = mean_or_none(get_vals(system_runs, "system_accuracy"))
    if accuracy is None:
        print("  fig9: skipped (no system accuracy)")
        return

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 3.8), gridspec_kw={"width_ratios": [1, 3]})
    acc_bar = ax1.bar(["Prompted\nRAG Prototype"], [accuracy], color=[BLUE], width=0.5,
                      edgecolor="white", linewidth=0.8, zorder=3)
    ax1.axhline(y=0.80, color=TARGET_COLOR, linewidth=1.2, linestyle="--", zorder=2)
    for bar in acc_bar:
        ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.03, f"{accuracy:.1%}",
                 ha="center", va="bottom", fontsize=8, fontweight="bold")
    ax1.set_ylim(0, 1.15)
    ax1.set_ylabel("Accuracy")
    ax1.set_title(f"Prompted Prototype Accuracy\n(n={len(system_runs)} runs)")
    ax1.tick_params(labelsize=8)

    metric_specs = [
        ("Faithfulness", mean_or_none(get_vals(system_runs, "system_avg_faithfulness")), 0.85, "higher"),
        ("Hallucination\nRate", mean_or_none(get_vals(system_runs, "system_avg_hallucination_rate")), 0.10, "lower"),
        ("Citation\nExistence", mean_or_none(get_vals(system_runs, "system_avg_citation_existence")), 0.90, "higher"),
        ("Precision@5", mean_or_none(get_vals(system_runs, "system_avg_precision_at_5")), None, "higher"),
        ("MRR", mean_or_none(get_vals(system_runs, "system_avg_mrr")), None, "higher"),
        ("Citation F1", mean_or_none(get_vals(system_runs, "system_avg_citation_f1")), 0.90, "higher"),
    ]
    available = [(label, value, target, direction) for label, value, target, direction in metric_specs if value is not None]
    names = [label for label, *_ in available]
    values = [value for _, value, _, _ in available]
    targets = [target for _, _, target, _ in available]
    directions = [direction for _, _, _, direction in available]
    x = np.arange(len(names))
    bars = ax2.bar(x, values, color=BLUE, width=0.58, edgecolor="white", linewidth=0.8, zorder=3)
    for i, target in enumerate(targets):
        if target is not None:
            ax2.plot([i - 0.35, i + 0.35], [target, target], color=TARGET_COLOR, linewidth=1.5, linestyle="--", zorder=4)
    for bar, value in zip(bars, values):
        ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.025, f"{value:.3f}",
                 ha="center", va="bottom", fontsize=7.5, fontweight="bold")
    ax2.set_xticks(x)
    ax2.set_xticklabels(names, fontsize=8)
    ax2.set_ylim(0, 1.2)
    ax2.set_ylabel("Score")
    ax2.set_title("Documented Prototype Metrics")
    ax2.legend(handles=[Line2D([0], [0], color=TARGET_COLOR, linewidth=1.5, linestyle="--", label="Target threshold")],
               fontsize=7, loc="upper right", framealpha=0.9)

    plt.tight_layout()
    out = FIGURES / "fig9_system_actuals.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  {out.name}")


def fig10_planning_overview(planning_runs: list[dict]) -> None:
    if not planning_runs:
        print("  fig10: skipped (no planning-system eval results)")
        return

    total_vals = get_vals(planning_runs, "n_scenarios")
    completed_vals = get_vals(planning_runs, "planning_scored_scenarios")
    incomplete_vals = get_vals(planning_runs, "planning_incomplete_for_planner")
    lookup_vals = get_vals(planning_runs, "planning_source_case_lookup_failures")
    total = mean_or_none(total_vals) or 0.0

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.5, 3.8), gridspec_kw={"width_ratios": [1.2, 2]})
    completeness_names = ["Completed", "Incomplete", "Lookup\nFailures"]
    completeness_counts = [
        mean_or_none(completed_vals) or 0.0,
        mean_or_none(incomplete_vals) or 0.0,
        mean_or_none(lookup_vals) or 0.0,
    ]
    completeness_rates = [count / total if total else 0.0 for count in completeness_counts]
    completeness_colors = [BLUE, ORANGE, GRAY]
    bars = ax1.bar(completeness_names, completeness_rates, color=completeness_colors, edgecolor="white", linewidth=0.8)
    for bar, count in zip(bars, completeness_counts):
        ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.03, f"{count:.1f}/{total:.0f}",
                 ha="center", va="bottom", fontsize=8, fontweight="bold")
    ax1.set_ylim(0, 1.15)
    ax1.set_ylabel("Share of scenarios")
    ax1.set_title(f"Planning Completeness (n={len(planning_runs)} runs)")

    metric_specs = [
        ("Accuracy", mean_or_none(get_vals(planning_runs, "planning_system_accuracy")), 0.80, "higher"),
        ("Faithfulness", mean_or_none(get_vals(planning_runs, "planning_system_avg_faithfulness")), 0.85, "higher"),
        ("Hallucination\nRate", mean_or_none(get_vals(planning_runs, "planning_system_avg_hallucination_rate")), 0.10, "lower"),
        ("Citation\nExistence", mean_or_none(get_vals(planning_runs, "planning_system_avg_citation_existence")), 0.90, "higher"),
        ("Citation F1", mean_or_none(get_vals(planning_runs, "planning_system_avg_citation_f1")), 0.90, "higher"),
    ]
    available = [(label, value, target, direction) for label, value, target, direction in metric_specs if value is not None]
    names = [label for label, *_ in available]
    values = [value for _, value, _, _ in available]
    targets = [target for _, _, target, _ in available]
    directions = [direction for _, _, _, direction in available]
    x = np.arange(len(names))
    bars2 = ax2.bar(x, values, color=BLUE, width=0.58, edgecolor="white", linewidth=0.8, zorder=3)
    for i, target in enumerate(targets):
        ax2.plot([i - 0.35, i + 0.35], [target, target], color=TARGET_COLOR, linewidth=1.5, linestyle="--", zorder=4)
    for bar, value in zip(bars2, values):
        ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.025, f"{value:.3f}",
                 ha="center", va="bottom", fontsize=7.5, fontweight="bold")
    ax2.set_xticks(x)
    ax2.set_xticklabels(names, fontsize=8)
    ax2.set_ylim(0, 1.2)
    ax2.set_ylabel("Score")
    completed_avg = mean_or_none(completed_vals) or 0.0
    ax2.set_title(f"Planning Quality On Completed Cases\n(avg completed n={completed_avg:.1f} / {total:.0f})")
    ax2.legend(handles=[Line2D([0], [0], color=TARGET_COLOR, linewidth=1.5, linestyle="--", label="Target threshold")],
               fontsize=7, loc="upper right", framealpha=0.9)

    plt.tight_layout()
    out = FIGURES / "fig10_planning_overview.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  {out.name}")


def main() -> None:
    print("Loading current-batch data...")
    baseline_runs, system_runs = load_eval_runs()
    planning_runs = load_planning_runs()
    constraint_data = load_constraint()
    rv_data = load_retrieval_verification()
    comparison_data = load_retrieval_comparison()

    print(f"  Baseline runs: {len(baseline_runs)}")
    print(f"  Prototype system runs: {len(system_runs)}")
    print(f"  Planning-system runs: {len(planning_runs)}")
    print(f"  Constraint data: {'yes' if constraint_data else 'no'}")
    print(f"  Retrieval verification: {'yes' if rv_data else 'no'}")
    print(f"  Retrieval comparison: {'yes' if comparison_data else 'no'}")

    print("\nGenerating figures...")
    fig_tree_vs_bm25(comparison_data)
    if baseline_runs:
        fig1_baselines(baseline_runs)
        fig2_heatmap(baseline_runs)
    fig3_constraints(constraint_data)
    fig4_retrieval(rv_data)
    if baseline_runs:
        fig5_hallucination(baseline_runs, system_runs)
    if baseline_runs and system_runs:
        fig6_system_comparison(baseline_runs, system_runs)
    if system_runs:
        fig7_system_heatmap(system_runs)
    fig8_scorecard(baseline_runs, system_runs, constraint_data, rv_data)
    fig9_system_actuals(system_runs)
    fig10_planning_overview(planning_runs)

    print(f"\nAll figures saved to {FIGURES}/")


if __name__ == "__main__":
    main()
