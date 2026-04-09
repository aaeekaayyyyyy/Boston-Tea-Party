"""
Boston Tea Party 2.0 -- Final Presentation Figures
Reads all eval result files and generates publication-quality charts.

Usage:
    python generate_final_figures.py

Reads from:
    eval/results/eval_*.json          (baseline and system runs, auto-detected)
    eval/results/constraint_*.json    (constraint benchmark)
    eval/results/retrieval_verification_*.json

Outputs to: eval/figures/
"""
import json
import glob
import numpy as np
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
import seaborn as sns

# -- Config --------------------------------------------------------------------

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
GRAY = "#bdc3c7"
TARGET_COLOR = "#333333"


# -- Load data -----------------------------------------------------------------

def load_eval_runs():
    """Load all eval runs and separate into baseline vs system."""
    files = sorted(glob.glob(str(RESULTS / "eval_*.json")))
    baselines, systems = [], []
    for f in files:
        with open(f) as fh:
            d = json.load(fh)
            s = d.get("summary", {})
            if "system_accuracy" in s:
                systems.append(d)
            elif "baseline_a_accuracy" in s:
                baselines.append(d)
    return baselines, systems


def load_constraint():
    files = sorted(glob.glob(str(RESULTS / "constraint_*.json")))
    if not files:
        return None
    with open(files[-1]) as f:
        return json.load(f)


def load_retrieval_verification():
    files = sorted(glob.glob(str(RESULTS / "retrieval_verification_*.json")))
    if not files:
        return None
    with open(files[-1]) as f:
        return json.load(f)


def get_vals(runs, key):
    return [r["summary"][key] for r in runs if key in r.get("summary", {})]


def mean_or_none(values):
    """Return the mean of a non-empty list, otherwise None."""
    if not values:
        return None
    return float(np.mean(values))


# -- Figure 1: Baseline Metrics with Error Bars --------------------------------

def fig1_baselines(runs):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 3.5),
                                   gridspec_kw={"width_ratios": [1, 2]})
    n = len(runs)

    a_vals = get_vals(runs, "baseline_a_accuracy")
    b_vals = get_vals(runs, "baseline_b_accuracy")
    cats = ["Baseline A\n(zero-shot)", "Baseline B\n(gold sources)"]
    means = [np.mean(a_vals), np.mean(b_vals)]
    stds = [np.std(a_vals), np.std(b_vals)]

    bars = ax1.bar(cats, means, yerr=stds, color=[BLUE, ORANGE], width=0.5,
                   edgecolor="white", linewidth=0.8, zorder=3, capsize=4,
                   error_kw={"linewidth": 1.2, "color": "#333"})
    ax1.axhline(y=0.80, color=TARGET_COLOR, linewidth=1.2, linestyle="--", zorder=2)
    for bar, m, s in zip(bars, means, stds):
        label = f"{m:.1%}" if s < 0.001 else f"{m:.1%} +/- {s:.1%}"
        ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + s + 0.025,
                 label, ha="center", va="bottom", fontsize=8, fontweight="bold")
    ax1.set_ylim(0, 1.15)
    ax1.set_ylabel("Accuracy")
    ax1.set_title(f"Answer Correctness (n={n})")
    ax1.tick_params(labelsize=8)

    metric_defs = [
        ("baseline_b_avg_faithfulness", "Faithfulness", 0.85, "higher"),
        ("baseline_b_avg_hallucination_rate", "Hallucination\nRate", 0.10, "lower"),
        ("baseline_b_avg_citation_existence", "Citation\nExistence", 0.90, "higher"),
        ("baseline_b_avg_citation_f1", "Citation F1", 0.90, "higher"),
    ]

    names = [m[1] for m in metric_defs]
    metric_values = []
    for key, *_rest in metric_defs:
        vals = get_vals(runs, key)
        metric_values.append(vals)
    m_means = [np.mean(vals) for vals in metric_values]
    m_stds = [np.std(vals) for vals in metric_values]
    targets = [m[2] for m in metric_defs]
    directions = [m[3] for m in metric_defs]

    colors = []
    for v, t, d in zip(m_means, targets, directions):
        colors.append(PASS_COLOR if (v >= t if d == "higher" else v <= t) else FAIL_COLOR)

    x = np.arange(len(names))
    bars2 = ax2.bar(x, m_means, yerr=m_stds, color=colors, width=0.55,
                    edgecolor="white", linewidth=0.8, zorder=3, capsize=4,
                    error_kw={"linewidth": 1.2, "color": "#333"})
    for i, t in enumerate(targets):
        ax2.plot([i - 0.35, i + 0.35], [t, t], color=TARGET_COLOR,
                 linewidth=1.5, linestyle="--", zorder=4)
    for bar, m, s in zip(bars2, m_means, m_stds):
        label = f"{m:.3f}" if s < 0.001 else f"{m:.2f}+/-{s:.2f}"
        ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + s + 0.025,
                 label, ha="center", va="bottom", fontsize=7.5, fontweight="bold")
    ax2.set_xticks(x)
    ax2.set_xticklabels(names, fontsize=8)
    ax2.set_ylim(0, 1.2)
    ax2.set_ylabel("Score")
    ax2.set_title(f"Baseline B Quality Metrics (n={n})")

    legend = [
        mpatches.Patch(facecolor=PASS_COLOR, label="Meets target"),
        mpatches.Patch(facecolor=FAIL_COLOR, label="Below target (expected for baseline)"),
        Line2D([0], [0], color=TARGET_COLOR, linewidth=1.5, linestyle="--", label="Target threshold"),
    ]
    ax2.legend(handles=legend, fontsize=7, loc="upper right", framealpha=0.9)

    plt.tight_layout()
    out = FIGURES / "fig1_baselines.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  {out.name}")


# -- Figure 2: Per-Scenario Heatmap -------------------------------------------

def fig2_heatmap(runs):
    latest = runs[-1]
    scenarios = latest["scenarios"]
    ids = [s["id"] for s in scenarios]
    metric_specs = [
        ("Answer\nCorrect", lambda data: 1.0 if data.get("answer_correct", False) else 0.0),
        ("Halluc.\nSafety", lambda data: 1.0 - data["hallucination_rate"] if "hallucination_rate" in data else np.nan),
        ("Faithful.", lambda data: data.get("faithfulness", 0.0)),
        ("Cite Exist.", lambda data: data.get("citation_existence", 0.0)),
        ("Cite F1", lambda data: data["citation_f1"] if "citation_f1" in data else np.nan),
    ]

    matrix = []
    for s in scenarios:
        b = s.get("baseline_b") or {}
        row = [getter(b) for _, getter in metric_specs]
        matrix.append(row)

    data = np.array(matrix, dtype=float)
    keep_cols = [i for i in range(data.shape[1]) if not np.isnan(data[:, i]).all()]
    data = data[:, keep_cols]
    metric_names = [metric_specs[i][0] for i in keep_cols]
    fig, ax = plt.subplots(figsize=(6, max(4, len(ids) * 0.45)))
    sns.heatmap(data, annot=True, fmt=".2f", cmap="RdYlGn", vmin=0, vmax=1,
                mask=np.isnan(data),
                xticklabels=metric_names, yticklabels=ids,
                linewidths=0.5, linecolor="#ddd", cbar_kws={"label": "Score"}, ax=ax)
    ax.set_title("Per-Scenario Baseline B Scores", pad=12)
    ax.set_ylabel("")
    ax.tick_params(axis="y", labelsize=8)
    ax.tick_params(axis="x", labelsize=9)

    plt.tight_layout()
    out = FIGURES / "fig2_heatmap.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  {out.name}")


# -- Figure 3: Constraint Engine -----------------------------------------------

def fig3_constraints(constraint_data):
    if not constraint_data:
        print("  fig3: skipped (no constraint data)")
        return

    domains = constraint_data["summary"]["per_domain"]
    names = [d.replace("_", " ").title() for d in domains]
    passed = [domains[d]["passed"] for d in domains]
    total = [domains[d]["cases"] for d in domains]
    f1s = [domains[d]["f1"] for d in domains]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 3.5),
                                   gridspec_kw={"width_ratios": [1.2, 1]})

    y = np.arange(len(names))
    failed = [t - p for p, t in zip(passed, total)]
    ax1.barh(y, passed, color=PASS_COLOR, label="Passed", edgecolor="white",
             linewidth=0.5, height=0.55)
    ax1.barh(y, failed, left=passed, color=FAIL_COLOR, label="Failed", edgecolor="white",
             linewidth=0.5, height=0.55)
    for i, (p, t) in enumerate(zip(passed, total)):
        ax1.text(t + 0.3, i, f"{p}/{t}", va="center", fontsize=9, fontweight="bold")
    ax1.set_yticks(y)
    ax1.set_yticklabels(names, fontsize=9)
    ax1.set_xlabel("Cases")
    ax1.set_title("Pass Rate by Domain")
    ax1.legend(loc="lower right", fontsize=8)
    ax1.set_xlim(0, max(total) + 2)
    ax1.invert_yaxis()

    bar_colors = [PASS_COLOR if f >= 0.9 else FAIL_COLOR for f in f1s]
    ax2.barh(y, f1s, color=bar_colors, edgecolor="white", linewidth=0.5, height=0.55)
    ax2.axvline(x=0.90, color=TARGET_COLOR, linewidth=2, linestyle="--", zorder=4)
    for i, f in enumerate(f1s):
        ax2.text(f + 0.01, i, f"{f:.3f}", va="center", fontsize=9, fontweight="bold")
    ax2.set_yticks(y)
    ax2.set_yticklabels(names, fontsize=9)
    ax2.set_xlabel("F1 Score")
    ax2.set_title("Element-Level F1 by Domain")
    ax2.set_xlim(0, 1.12)
    ax2.legend(
        handles=[Line2D([0], [0], color=TARGET_COLOR, linewidth=2, linestyle="--", label="Target (0.90)")],
        loc="lower right", fontsize=8,
    )
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


# -- Figure 4: Retrieval Verification -----------------------------------------

def fig4_retrieval(rv_data):
    if not rv_data:
        print("  fig4: skipped (no retrieval verification data)")
        return

    s = rv_data["summary"]
    checks = []
    golden = s.get("golden_retrieval")
    if golden:
        checks.append(
            ("Golden\nRetrieval", golden.get("passed", 0), golden.get("total", 0))
        )
    checks.extend([
        ("Source-Type\nConsistency",
         s["source_type_consistency"]["passed"],
         s["source_type_consistency"]["applicable"]),
        ("Tax-Year\nValidation",
         s["tax_year_validation"]["passed"],
         s["tax_year_validation"]["applicable"]),
        ("Provenance\nCompleteness",
         s["provenance_completeness"]["all_complete"],
         s["provenance_completeness"]["applicable"]),
    ])

    fig, ax = plt.subplots(figsize=(6, 3))
    names = [c[0] for c in checks]
    passed_vals = [c[1] for c in checks]
    total_vals = [c[2] for c in checks]
    rates = [p / t if t > 0 else 0 for p, t in zip(passed_vals, total_vals)]

    x = np.arange(len(names))
    colors = [PASS_COLOR if r == 1.0 else FAIL_COLOR for r in rates]
    bars = ax.bar(x, rates, color=colors, width=0.52, edgecolor="white", linewidth=0.8, zorder=3)

    for bar, p, t in zip(bars, passed_vals, total_vals):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.025,
                f"{p}/{t}", ha="center", va="bottom", fontsize=10, fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(names, fontsize=9)
    ax.set_ylim(0, 1.15)
    ax.set_ylabel("Pass Rate")
    ax.set_title("Retrieval Quality Checks", pad=10)

    plt.tight_layout()
    out = FIGURES / "fig4_retrieval.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  {out.name}")


# -- Figure 5: LettuceDetect Hallucination Per Scenario ------------------------

def fig5_hallucination(runs):
    latest = runs[-1]
    scenarios = latest["scenarios"]

    hal_data = []
    for s in scenarios:
        b = s.get("baseline_b") or {}
        rate = b.get("hallucination_rate")
        spans = b.get("hallucinated_spans", [])
        if rate is not None:
            hal_data.append({"id": s["id"], "rate": rate, "n_spans": len(spans)})
    hal_data.sort(key=lambda x: x["rate"], reverse=True)

    fig, ax = plt.subplots(figsize=(8, max(3, len(hal_data) * 0.4)))
    y = np.arange(len(hal_data))
    colors = [FAIL_COLOR if h["rate"] > 0.10 else PASS_COLOR for h in hal_data]
    ax.barh(y, [h["rate"] for h in hal_data], color=colors, edgecolor="white",
            linewidth=0.5, height=0.6)
    ax.axvline(x=0.10, color=TARGET_COLOR, linewidth=2, linestyle="--", zorder=4)

    for i, h in enumerate(hal_data):
        ax.text(h["rate"] + 0.005, i,
                f'{h["rate"]:.3f}  ({h["n_spans"]} spans)',
                va="center", fontsize=8, color="#555")

    ax.set_yticks(y)
    ax.set_yticklabels([h["id"] for h in hal_data], fontsize=8)
    ax.set_xlabel("Hallucination Rate")
    ax.set_title("LettuceDetect Hallucination Rate by Scenario (Baseline B)")
    ax.legend(
        handles=[Line2D([0], [0], color=TARGET_COLOR, linewidth=2, linestyle="--", label="Target (0.10)")],
        loc="lower right", fontsize=8,
    )
    ax.invert_yaxis()
    ax.set_xlim(0, max(h["rate"] for h in hal_data) + 0.08)

    plt.tight_layout()
    out = FIGURES / "fig5_hallucination.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  {out.name}")


# -- Figure 6: System vs Baseline Comparison -----------------------------------

def fig6_system_comparison(baseline_runs, system_runs):
    if not system_runs:
        print("  fig6: skipped (no system results)")
        return

    sys_s = system_runs[-1]["summary"]
    metric_specs = [
        ("Answer\nCorrectness", mean_or_none(get_vals(baseline_runs, "baseline_b_accuracy")), sys_s.get("system_accuracy"), 0.80),
        ("Faithfulness", mean_or_none(get_vals(baseline_runs, "baseline_b_avg_faithfulness")), sys_s.get("system_avg_faithfulness"), 0.85),
        ("Hallucination\nRate", mean_or_none(get_vals(baseline_runs, "baseline_b_avg_hallucination_rate")),
         sys_s.get("system_avg_hallucination_rate"), 0.10),
        ("Citation\nExistence", mean_or_none(get_vals(baseline_runs, "baseline_b_avg_citation_existence")), sys_s.get("system_avg_citation_existence"), 0.90),
        ("Citation F1", mean_or_none(get_vals(baseline_runs, "baseline_b_avg_citation_f1")), sys_s.get("system_avg_citation_f1"), 0.90),
    ]
    available = [(label, b_val, s_val, target) for label, b_val, s_val, target in metric_specs if b_val is not None and s_val is not None]
    if not available:
        print("  fig6: skipped (no overlapping system metrics)")
        return
    metrics = [label for label, *_ in available]
    b_means = [b_val for _, b_val, _, _ in available]
    s_vals = [s_val for _, _, s_val, _ in available]
    targets = [target for _, _, _, target in available]

    fig, ax = plt.subplots(figsize=(10, 4.5))
    x = np.arange(len(metrics))
    w = 0.32
    ax.bar(x - w / 2, b_means, w, label="Baseline B (gold sources)",
           color=ORANGE, edgecolor="white", linewidth=0.8, zorder=3)
    ax.bar(x + w / 2, s_vals, w, label="RAG Pipeline (RAG + Constraints)",
           color=BLUE, edgecolor="white", linewidth=0.8, zorder=3)

    for i, t in enumerate(targets):
        ax.plot([i - 0.4, i + 0.4], [t, t], color=TARGET_COLOR,
                linewidth=1.2, linestyle="--", zorder=2)

    for i, (bv, sv) in enumerate(zip(b_means, s_vals)):
        ax.text(i - w / 2, bv + 0.02, f"{bv:.2f}", ha="center", va="bottom",
                 fontsize=7.5, fontweight="bold", color="#555")
        lower_better = metrics[i] == "Hallucination\nRate"
        color = PASS_COLOR if (sv <= bv if lower_better else sv >= bv) else FAIL_COLOR
        ax.text(i + w / 2, sv + 0.02, f"{sv:.2f}", ha="center", va="bottom",
                 fontsize=7.5, fontweight="bold", color=color)

    ax.set_xticks(x)
    ax.set_xticklabels(metrics, fontsize=9)
    ax.set_ylim(0, 1.2)
    ax.set_ylabel("Metric value")
    ax.set_title("RAG Pipeline vs. Baseline B", pad=10)
    ax.legend(fontsize=8, loc="upper left")

    plt.tight_layout()
    out = FIGURES / "fig6_system_vs_baseline.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  {out.name}")


# -- Figure 7: System Per-Scenario Heatmap -------------------------------------

def fig7_system_heatmap(system_runs):
    if not system_runs:
        print("  fig7: skipped (no system results)")
        return

    latest = system_runs[-1]
    scenarios = latest["scenarios"]
    ids = [
        f"{s['id']}*" if (s.get("system", {}) or {}).get("hallucination_truncated") else s["id"]
        for s in scenarios
    ]
    metric_specs = [
        ("Answer\nCorrect", lambda data: 1.0 if data.get("answer_correct", False) else 0.0),
        ("Halluc.\nSafety", lambda data: 1.0 - data["hallucination_rate"] if "hallucination_rate" in data else np.nan),
        ("Faithful.", lambda data: data.get("faithfulness", 0.0)),
        ("Cite Exist.", lambda data: data.get("citation_existence", 0.0)),
        ("Cite F1", lambda data: data["citation_f1"] if "citation_f1" in data else np.nan),
    ]

    matrix = []
    for s in scenarios:
        sys_data = s.get("system", {})
        row = [getter(sys_data) for _, getter in metric_specs]
        matrix.append(row)

    data = np.array(matrix, dtype=float)
    keep_cols = [i for i in range(data.shape[1]) if not np.isnan(data[:, i]).all()]
    data = data[:, keep_cols]
    metric_names = [metric_specs[i][0] for i in keep_cols]
    fig, ax = plt.subplots(figsize=(6, max(4, len(ids) * 0.45)))
    sns.heatmap(data, annot=True, fmt=".2f", cmap="RdYlGn", vmin=0, vmax=1,
                mask=np.isnan(data),
                xticklabels=metric_names, yticklabels=ids,
                linewidths=0.5, linecolor="#ddd", cbar_kws={"label": "Score"}, ax=ax)
    ax.set_title("Per-Scenario System Scores\n* hallucination scored on truncated context", pad=12)
    ax.set_ylabel("")
    ax.tick_params(axis="y", labelsize=8)
    ax.tick_params(axis="x", labelsize=9)

    plt.tight_layout()
    out = FIGURES / "fig7_system_heatmap.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  {out.name}")


# -- Figure 8: Summary Scorecard -----------------------------------------------

def fig8_scorecard(baseline_runs, system_runs, constraint_data, rv_data):
    rows = []

    if rv_data:
        s = rv_data["summary"]
        golden = s.get("golden_retrieval")
        if golden:
            gp, gt = golden.get("passed", 0), golden.get("total", 0)
            rows.append(("Golden Retrieval Quality", f"{gp}/{gt}",
                          f"{gp/gt:.0%}" if gt else "N/A", gp == gt if gt else False))
        sc = s["source_type_consistency"]
        sc_rate = f"{sc['passed']/sc['applicable']:.0%}" if sc['applicable'] else "N/A"
        rows.append(("Source-Type Consistency", f"{sc['passed']}/{sc['applicable']}", sc_rate,
                      sc["passed"] == sc["applicable"]))
        ty = s["tax_year_validation"]
        ty_rate = f"{ty['passed']/ty['applicable']:.0%}" if ty['applicable'] else "N/A"
        rows.append(("Tax-Year Validation", f"{ty['passed']}/{ty['applicable']}", ty_rate,
                      ty["passed"] == ty["applicable"]))
        pc = s["provenance_completeness"]
        pc_rate = f"{pc['all_complete']/pc['applicable']:.0%}" if pc['applicable'] else "N/A"
        rows.append(("Provenance Completeness", f"{pc['all_complete']}/{pc['applicable']}", pc_rate,
                      pc["all_complete"] == pc["applicable"]))

    if constraint_data:
        cs = constraint_data["summary"]
        rows.append(("Constraint Engine F1", f"{cs['cases_passed']}/{cs['n_cases']}",
                      f"{cs['f1']:.3f}", cs["f1"] >= 0.90))

    if baseline_runs:
        b_acc = np.mean(get_vals(baseline_runs, "baseline_b_accuracy"))
        rows.append(("Baseline B Accuracy", "", f"{b_acc:.1%}", b_acc >= 0.80))
        faith = np.mean(get_vals(baseline_runs, "baseline_b_avg_faithfulness"))
        rows.append(("Baseline B Faithfulness", "", f"{faith:.3f}", faith >= 0.85))
        hal = np.mean(get_vals(baseline_runs, "baseline_b_avg_hallucination_rate"))
        rows.append(("Baseline B Halluc. Safety", "", f"{1.0 - hal:.3f}", (1.0 - hal) >= 0.90))

    if system_runs:
        ss = system_runs[-1]["summary"]
        sa = ss.get("system_accuracy")
        if sa is not None:
            rows.append(("RAG Pipeline Accuracy", "", f"{sa:.1%}", sa >= 0.80))
        sf = ss.get("system_avg_faithfulness")
        if sf is not None:
            rows.append(("RAG Pipeline Faithfulness", "", f"{sf:.3f}", sf >= 0.85))
        sh = ss.get("system_avg_hallucination_rate")
        if sh is not None:
            rows.append(("RAG Pipeline Halluc. Safety", "", f"{1.0 - sh:.3f}", (1.0 - sh) >= 0.90))
        sce = ss.get("system_avg_citation_existence")
        if sce is not None:
            rows.append(("RAG Pipeline Cite Exist. (section)", "", f"{sce:.3f}", sce >= 0.90))
        scf = ss.get("system_avg_citation_f1")
        if scf is not None:
            rows.append(("RAG Pipeline Citation F1", "", f"{scf:.3f}", scf >= 0.90))
        ssce = ss.get("system_avg_source_citation_existence")
        if ssce is not None:
            rows.append(("RAG Pipeline Cite Exist. (source)", "", f"{ssce:.3f}", False))

    if not rows:
        print("  fig8: skipped (no data)")
        return

    fig, ax = plt.subplots(figsize=(8, max(3, len(rows) * 0.4 + 1)))
    ax.axis("off")

    col_labels = ["Metric", "Cases", "Score", "Status"]
    cell_text = []
    cell_colors = []
    for name, cases, score, is_pass in rows:
        status = "PASS" if is_pass else "BELOW TARGET"
        cell_text.append([name, cases, score, status])
        if is_pass:
            cell_colors.append(["#f0faf0", "#f0faf0", "#f0faf0", "#d4edda"])
        else:
            cell_colors.append(["#fef5f5", "#fef5f5", "#fef5f5", "#f8d7da"])

    table = ax.table(cellText=cell_text, colLabels=col_labels,
                     cellColours=cell_colors, loc="center", cellLoc="center")
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1.0, 1.4)

    for (row, col), cell in table.get_celld().items():
        if row == 0:
            cell.set_facecolor("#2c3e50")
            cell.set_text_props(color="white", fontweight="bold")
        cell.set_edgecolor("#ddd")

    ax.set_title("Evaluation Scorecard", fontsize=13, fontweight="bold", pad=15)

    plt.tight_layout()
    out = FIGURES / "fig8_scorecard.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  {out.name}")


def fig9_system_actuals(system_runs, constraint_data, rv_data):
    """System-only companion to Figure 1 using the latest measured results."""
    if not system_runs:
        print("  fig9: skipped (no system results)")
        return

    sys_s = system_runs[-1]["summary"]
    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(11, 3.8), gridspec_kw={"width_ratios": [1, 3]}
    )

    accuracy = sys_s.get("system_accuracy")
    if accuracy is None:
        print("  fig9: skipped (no system accuracy)")
        plt.close(fig)
        return

    acc_bar = ax1.bar(
        ["RAG Pipeline"], [accuracy], color=[BLUE], width=0.5,
        edgecolor="white", linewidth=0.8, zorder=3,
    )
    ax1.axhline(y=0.80, color=TARGET_COLOR, linewidth=1.2, linestyle="--", zorder=2)
    for bar in acc_bar:
        ax1.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.03,
            f"{accuracy:.1%}",
            ha="center",
            va="bottom",
            fontsize=8,
            fontweight="bold",
        )
    ax1.set_ylim(0, 1.15)
    ax1.set_ylabel("Accuracy")
    ax1.set_title("System Accuracy")
    ax1.tick_params(labelsize=8)

    metric_specs = []
    if constraint_data:
        metric_specs.append(("Constraint\nF1", constraint_data["summary"].get("f1"), 0.90, "higher"))
    metric_specs.extend([
        ("Faithfulness", sys_s.get("system_avg_faithfulness"), 0.85, "higher"),
        ("Hallucination\nRate", sys_s.get("system_avg_hallucination_rate"), 0.10, "lower"),
        ("Citation\nExistence", sys_s.get("system_avg_citation_existence"), 0.90, "higher"),
        ("Precision@5", sys_s.get("system_avg_precision_at_5"), None, "higher"),
        ("MRR", sys_s.get("system_avg_mrr"), None, "higher"),
    ])
    if "system_avg_citation_f1" in sys_s:
        metric_specs.append(("Citation F1", sys_s.get("system_avg_citation_f1"), 0.90, "higher"))

    available = [(label, value, target, direction) for label, value, target, direction in metric_specs if value is not None]
    names = [label for label, *_ in available]
    values = [value for _, value, _, _ in available]
    targets = [target for _, _, target, _ in available]
    directions = [direction for _, _, _, direction in available]

    colors = []
    for value, target, direction in zip(values, targets, directions):
        if target is None:
            colors.append(BLUE)
        else:
            colors.append(PASS_COLOR if (value >= target if direction == "higher" else value <= target) else FAIL_COLOR)

    x = np.arange(len(names))
    bars2 = ax2.bar(
        x, values, color=colors, width=0.58,
        edgecolor="white", linewidth=0.8, zorder=3,
    )
    for i, target in enumerate(targets):
        if target is not None:
            ax2.plot([i - 0.35, i + 0.35], [target, target], color=TARGET_COLOR,
                     linewidth=1.5, linestyle="--", zorder=4)
    for bar, value in zip(bars2, values):
        ax2.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.025,
            f"{value:.3f}",
            ha="center",
            va="bottom",
            fontsize=7.5,
            fontweight="bold",
        )

    ax2.set_xticks(x)
    ax2.set_xticklabels(names, fontsize=8)
    ax2.set_ylim(0, 1.2)
    ax2.set_ylabel("Score")
    ax2.set_title("Documented Key System Metrics")

    legend = [
        mpatches.Patch(facecolor=PASS_COLOR, label="Meets target"),
        mpatches.Patch(facecolor=FAIL_COLOR, label="Below target"),
        mpatches.Patch(facecolor=BLUE, label="Measured (no target)"),
        Line2D([0], [0], color=TARGET_COLOR, linewidth=1.5, linestyle="--", label="Target threshold"),
    ]
    ax2.legend(handles=legend, fontsize=7, loc="upper right", framealpha=0.9)

    plt.tight_layout()
    out = FIGURES / "fig9_system_actuals.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  {out.name}")


# -- Main ----------------------------------------------------------------------

def main():
    print("Loading data...")
    baseline_runs, system_runs = load_eval_runs()
    constraint_data = load_constraint()
    rv_data = load_retrieval_verification()

    print(f"  Baseline runs: {len(baseline_runs)}")
    print(f"  System runs: {len(system_runs)}")
    print(f"  Constraint data: {'yes' if constraint_data else 'no'}")
    print(f"  Retrieval verification: {'yes' if rv_data else 'no'}")

    print("\nGenerating figures...")
    if baseline_runs:
        fig1_baselines(baseline_runs)
        fig2_heatmap(baseline_runs)
        fig5_hallucination(baseline_runs)
    fig3_constraints(constraint_data)
    fig4_retrieval(rv_data)
    if baseline_runs:
        fig6_system_comparison(baseline_runs, system_runs)
    if system_runs:
        fig7_system_heatmap(system_runs)
    fig8_scorecard(baseline_runs, system_runs, constraint_data, rv_data)
    fig9_system_actuals(system_runs, constraint_data, rv_data)

    print(f"\nAll figures saved to {FIGURES}/")


if __name__ == "__main__":
    main()
