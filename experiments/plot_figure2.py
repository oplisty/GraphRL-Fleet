from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean, stdev

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
BASELINES_DIR = ROOT / "experiments" / "baselines"
QLEARNING_DIR = ROOT / "experiments" / "qlearning"
OUTPUT_DIR = ROOT / "experiments" / "figures" / "main"
OUTPUT_PATH = OUTPUT_DIR / "fig_qlearning_vs_best_baseline.pdf"

SCALES = ["small", "medium"]
BASELINE_SCHEDULERS = ["nearest", "earliest_deadline", "heaviest"]
BASELINE_LABELS = {
    "nearest": "Nearest",
    "earliest_deadline": "EDF",
    "heaviest": "Heaviest",
}
QLEARNING_MODELS = ["small", "medium", "mixed"]
MODEL_LABELS = {
    "small": "Train: Small",
    "medium": "Train: Medium",
    "mixed": "Train: Mixed",
}
METHODS_BY_SCALE = {
    "small": ["baseline", "small", "mixed"],
    "medium": ["baseline", "medium"],
}

PALETTE = {
    "baseline": "#F38181",
    "baseline_highlight": "#F38181",
    "small": "#95E1D3",
    "medium": "#FCE38A",
    "mixed": "#EAFFD0",
    "mixed_highlight": "#EAFFD0",
}

METRICS = [
    ("final_score", "Final Score", False),
    ("completed_tasks", "Completed Tasks", False),
    ("expired_tasks", "Expired Tasks", True),
]

plt.rcParams.update(
    {
        "font.family": "serif",
        "font.serif": ["Times New Roman", "Times", "Nimbus Roman", "DejaVu Serif"],
        "mathtext.fontset": "stix",
        "font.size": 11,
        "axes.titlesize": 12,
        "axes.labelsize": 11,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "legend.fontsize": 10,
        "figure.dpi": 160,
        "savefig.dpi": 320,
    }
)


def _safe_stdev(values: list[float]) -> float:
    if len(values) <= 1:
        return 0.0
    return stdev(values)


def _read_step_summary(step_csv: Path) -> dict[str, float]:
    with step_csv.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError(f"Empty step log: {step_csv}")
    last = rows[-1]
    return {
        "final_score": float(last["total_score"]),
        "completed_tasks": float(last["completed_tasks"]),
        "expired_tasks": float(last["expired_tasks"]),
    }


def collect_baseline_best() -> dict[str, dict[str, tuple[str, float, float]]]:
    data: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

    for scale in SCALES:
        for scheduler in BASELINE_SCHEDULERS:
            pattern = f"{scale}_{scheduler}_seed*"
            for run_dir in BASELINES_DIR.glob(pattern):
                inner_dir = run_dir / f"{scale}_{scheduler}"
                step_csv = inner_dir / "step_log.csv"
                if not step_csv.exists():
                    continue
                summary = _read_step_summary(step_csv)
                for metric_name, _, _ in METRICS:
                    data[f"{scale}:{scheduler}"][metric_name].append(summary[metric_name])

    best_summary: dict[str, dict[str, tuple[str, float, float]]] = defaultdict(dict)
    for scale in SCALES:
        scheduler_stats: dict[str, dict[str, tuple[float, float]]] = {}
        for scheduler in BASELINE_SCHEDULERS:
            key = f"{scale}:{scheduler}"
            stats_for_scheduler: dict[str, tuple[float, float]] = {}
            for metric_name, _, _ in METRICS:
                values = data[key][metric_name]
                if not values:
                    raise ValueError(f"Missing baseline values for {scale}/{scheduler}/{metric_name}")
                stats_for_scheduler[metric_name] = (mean(values), _safe_stdev(values))
            scheduler_stats[scheduler] = stats_for_scheduler

        for metric_name, _, lower_is_better in METRICS:
            metric_scores = {scheduler: scheduler_stats[scheduler][metric_name][0] for scheduler in BASELINE_SCHEDULERS}
            if lower_is_better:
                best_scheduler = min(metric_scores, key=metric_scores.get)
            else:
                best_scheduler = max(metric_scores, key=metric_scores.get)
            best_mean, best_std = scheduler_stats[best_scheduler][metric_name]
            best_summary[scale][metric_name] = (best_scheduler, best_mean, best_std)

    return best_summary


def collect_qlearning_summary() -> dict[str, dict[str, tuple[float, float]]]:
    summary: dict[str, dict[str, tuple[float, float]]] = {}
    for model_name in QLEARNING_MODELS:
        eval_csv = QLEARNING_DIR / model_name / "eval_summary.csv"
        if not eval_csv.exists():
            raise FileNotFoundError(f"Missing Q-learning eval summary: {eval_csv}")

        values_by_metric: dict[str, list[float]] = defaultdict(list)
        with eval_csv.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                for metric_name, _, _ in METRICS:
                    values_by_metric[metric_name].append(float(row[metric_name]))

        model_summary: dict[str, tuple[float, float]] = {}
        for metric_name, _, _ in METRICS:
            values = values_by_metric[metric_name]
            if not values:
                raise ValueError(f"Missing Q-learning values for {model_name}/{metric_name}")
            model_summary[metric_name] = (mean(values), _safe_stdev(values))
        summary[model_name] = model_summary

    return summary


def _beautify_axis(ax: plt.Axes) -> None:
    ax.set_axisbelow(True)
    ax.grid(axis="y", linestyle="-", linewidth=0.7, alpha=0.18)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_alpha(0.22)
    ax.spines["bottom"].set_alpha(0.22)


def plot_figure(
    baseline_best: dict[str, dict[str, tuple[str, float, float]]],
    qlearning_summary: dict[str, dict[str, tuple[float, float]]],
) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(1, 3, figsize=(12.4, 4.6), constrained_layout=True)

    x = np.arange(len(SCALES))
    width = 0.22
    legend_seen: set[str] = set()

    for ax, (metric_name, metric_label, _) in zip(axes, METRICS):
        for scale_idx, scale in enumerate(SCALES):
            methods = METHODS_BY_SCALE[scale]
            offsets = (np.arange(len(methods)) - (len(methods) - 1) / 2.0) * width * 1.12

            for offset, method in zip(offsets, methods):
                if method == "baseline":
                    _, best_mean, best_std = baseline_best[scale][metric_name]
                    mean_value = best_mean
                    std_value = best_std
                else:
                    model_mean, model_std = qlearning_summary[method][metric_name]
                    mean_value = model_mean
                    std_value = model_std

                color = PALETTE[method if method != "baseline" else "baseline"]
                if method == "baseline":
                    color = PALETTE["baseline_highlight"]

                legend_key = method
                label = "Best Baseline" if method == "baseline" else MODEL_LABELS[method]
                if legend_key in legend_seen:
                    label = "_nolegend_"
                legend_seen.add(legend_key)

                ax.bar(
                    x[scale_idx] + offset,
                    mean_value,
                    width,
                    label=label,
                    color=color,
                    edgecolor="none",
                    linewidth=0,
                    yerr=std_value,
                    ecolor="#555555",
                    capsize=4,
                    error_kw={"elinewidth": 1.0, "capthick": 1.0},
                    zorder=3,
                )

        ax.set_xticks(x)
        ax.set_xticklabels([s.capitalize() for s in SCALES])
        ax.set_xlabel("Test Scale")
        ax.set_ylabel(metric_label)
        _beautify_axis(ax)

    handles = [
        plt.Rectangle((0, 0), 1, 1, facecolor=PALETTE["baseline_highlight"], edgecolor="none"),
        plt.Rectangle((0, 0), 1, 1, facecolor=PALETTE["small"], edgecolor="none"),
        plt.Rectangle((0, 0), 1, 1, facecolor=PALETTE["medium"], edgecolor="none"),
        plt.Rectangle((0, 0), 1, 1, facecolor=PALETTE["mixed"], edgecolor="none"),
    ]
    labels = ["Best Baseline", "Train: Small", "Train: Medium", "Train: Mixed"]
    fig.legend(handles, labels, loc="upper center", ncol=4, frameon=False, bbox_to_anchor=(0.5, 1.04))

    fig.savefig(OUTPUT_PATH, bbox_inches="tight")
    return OUTPUT_PATH


def main() -> None:
    baseline_best = collect_baseline_best()
    qlearning_summary = collect_qlearning_summary()
    output_path = plot_figure(baseline_best, qlearning_summary)
    print(f"Saved Figure 2 to: {output_path}")


if __name__ == "__main__":
    main()
