from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean, stdev

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
ABLATION_BASELINE_DIR = ROOT / "experiments" / "ablation" / "charging"
ABLATION_Q_DIR = ROOT / "experiments" / "ablation" / "qlearning_charging"
OUTPUT_DIR = ROOT / "experiments" / "figures" / "main"
OUTPUT_PATH = OUTPUT_DIR / "fig_charging_ablation.pdf"

STRATEGIES = ["optimal_station", "nearest_station"]
METHODS = ["baseline", "qlearning"]
METHOD_LABELS = {
    "baseline": "Baseline",
    "qlearning": "Q-learning",
}
STRATEGY_LABELS = {
    "optimal_station": "Full: optimal station",
    "nearest_station": "Ablated: nearest station",
}
SEEDS = [7, 8, 9, 10, 11]

PALETTE = {
    "positive": "#95E1D3",
    "negative": "#F38181",
    "zero": "#FCE38A",
    "guide": "#777777",
}
METRICS = [
    ("final_score", "Delta Final Score", "higher"),
    ("completed_tasks", "Delta Completed Tasks", "higher"),
    ("expired_tasks", "Expired Reduction", "lower"),
]

plt.rcParams.update(
    {
        "font.family": "serif",
        "font.serif": ["Times New Roman", "Times", "Nimbus Roman", "DejaVu Serif"],
        "mathtext.fontset": "stix",
        "font.size": 14,
        "axes.titlesize": 15,
        "axes.labelsize": 14,
        "xtick.labelsize": 13,
        "ytick.labelsize": 13,
        "legend.fontsize": 16,
        "figure.dpi": 160,
        "savefig.dpi": 320,
    }
)


def _safe_stdev(values: list[float]) -> float:
    if len(values) <= 1:
        return 0.0
    return stdev(values)


def _read_baseline_step_summary(path: Path) -> dict[str, float]:
    with path.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError(f"Empty step log: {path}")
    last = rows[-1]
    return {
        "final_score": float(last["total_score"]),
        "completed_tasks": float(last["completed_tasks"]),
        "expired_tasks": float(last["expired_tasks"]),
    }


def collect_baseline_ablation() -> dict[str, dict[str, tuple[float, float]]]:
    values: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

    for strategy in STRATEGIES:
        for seed in SEEDS:
            run_dir = ABLATION_BASELINE_DIR / f"{strategy}_seed{seed}" / "medium_nearest"
            step_csv = run_dir / "step_log.csv"
            if not step_csv.exists():
                raise FileNotFoundError(f"Missing ablation baseline files in {run_dir}")

            summary = _read_baseline_step_summary(step_csv)

            for metric_name, _, _ in METRICS:
                values[strategy][metric_name].append(summary[metric_name])

    summary: dict[str, dict[str, tuple[float, float]]] = {}
    for strategy in STRATEGIES:
        summary[strategy] = {}
        for metric_name, _, _ in METRICS:
            metric_values = values[strategy][metric_name]
            summary[strategy][metric_name] = (mean(metric_values), _safe_stdev(metric_values))
    return summary


def collect_qlearning_ablation() -> dict[str, dict[str, tuple[float, float]]]:
    summary: dict[str, dict[str, tuple[float, float]]] = {}
    for strategy in STRATEGIES:
        eval_csv = ABLATION_Q_DIR / strategy / "eval_summary.csv"
        if not eval_csv.exists():
            raise FileNotFoundError(f"Missing Q-learning ablation eval summary: {eval_csv}")

        values: dict[str, list[float]] = defaultdict(list)
        with eval_csv.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                values["final_score"].append(float(row["final_score"]))
                values["completed_tasks"].append(float(row["completed_tasks"]))
                values["expired_tasks"].append(float(row["expired_tasks"]))

        summary[strategy] = {}
        for metric_name, _, _ in METRICS:
            metric_values = values[metric_name]
            summary[strategy][metric_name] = (mean(metric_values), _safe_stdev(metric_values))
    return summary


def _effect_value(
    full_value: float,
    ablated_value: float,
    direction: str,
) -> float:
    if direction == "higher":
        return full_value - ablated_value
    if direction == "lower":
        return ablated_value - full_value
    raise ValueError(f"Unknown metric direction: {direction}")


def compute_ablation_effects(
    baseline_summary: dict[str, dict[str, tuple[float, float]]],
    qlearning_summary: dict[str, dict[str, tuple[float, float]]],
) -> dict[str, dict[str, float]]:
    method_to_summary = {
        "baseline": baseline_summary,
        "qlearning": qlearning_summary,
    }
    effects: dict[str, dict[str, float]] = defaultdict(dict)
    for method in METHODS:
        for metric_name, _, direction in METRICS:
            full_value = method_to_summary[method]["optimal_station"][metric_name][0]
            ablated_value = method_to_summary[method]["nearest_station"][metric_name][0]
            effects[method][metric_name] = _effect_value(full_value, ablated_value, direction)
    return effects


def _format_effect(metric_name: str, value: float) -> str:
    if abs(value) < 0.05:
        return "0"
    if metric_name == "final_score":
        return f"{value:+.1f}"
    return f"{value:+.1f}"


def _beautify_axis(ax: plt.Axes) -> None:
    ax.set_axisbelow(True)
    ax.grid(axis="x", linestyle="-", linewidth=0.7, alpha=0.18)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_alpha(0.22)
    ax.spines["bottom"].set_alpha(0.22)


def plot_figure(
    baseline_summary: dict[str, dict[str, tuple[float, float]]],
    qlearning_summary: dict[str, dict[str, tuple[float, float]]],
) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    effects = compute_ablation_effects(baseline_summary, qlearning_summary)
    fig, axes = plt.subplots(1, 3, figsize=(10.8, 3.35), constrained_layout=True, sharey=True)
    y_positions = np.arange(len(METHODS))[::-1]
    y_labels = [METHOD_LABELS[method] for method in METHODS]

    for ax, (metric_name, metric_label, _) in zip(axes, METRICS):
        values = [effects[method][metric_name] for method in METHODS]
        max_abs = max(max(abs(value) for value in values), 1.0)
        pad = max_abs * 0.25
        ax.axvline(0, color=PALETTE["guide"], linewidth=1.0, alpha=0.72, zorder=2)

        for y, method, value in zip(y_positions, METHODS, values):
            if value > 0:
                color = PALETTE["positive"]
            elif value < 0:
                color = PALETTE["negative"]
            else:
                color = PALETTE["zero"]

            ax.barh(
                y,
                value,
                height=0.34,
                color=color,
                edgecolor="none",
                zorder=3,
            )
            label_x = value + (max_abs * 0.05 if value >= 0 else -max_abs * 0.05)
            ax.text(
                label_x,
                y,
                _format_effect(metric_name, value),
                va="center",
                ha="left" if value >= 0 else "right",
                fontsize=10,
                color="#333333",
            )

        ax.set_xlim(-max_abs - pad, max_abs + pad)
        ax.set_yticks(y_positions)
        ax.set_yticklabels(y_labels)
        ax.set_xlabel(metric_label)
        _beautify_axis(ax)

    fig.savefig(OUTPUT_PATH, bbox_inches="tight")
    return OUTPUT_PATH


def main() -> None:
    baseline_summary = collect_baseline_ablation()
    qlearning_summary = collect_qlearning_ablation()
    output_path = plot_figure(baseline_summary, qlearning_summary)
    print(f"Saved Figure 4 to: {output_path}")


if __name__ == "__main__":
    main()
