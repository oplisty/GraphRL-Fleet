from __future__ import annotations

import csv
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean, stdev

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
BASELINES_DIR = ROOT / "experiments" / "baselines"
OUTPUT_DIR = ROOT / "experiments" / "figures" / "main"
OUTPUT_PATH = OUTPUT_DIR / "fig_baseline_multi_scale.pdf"

SCALES = ["small", "medium", "large"]
SCHEDULERS = ["nearest", "earliest_deadline", "heaviest"]
SCHEDULER_LABELS = {
    "nearest": "Nearest",
    "earliest_deadline": "EDF",
    "heaviest": "Heaviest",
}

# User-requested palette.
PALETTE = {
    "nearest": "#95E1D3",
    "earliest_deadline": "#FCE38A",
    "heaviest": "#EAFFD0",
    "accent_1": "#F38181",
    "accent_2": "#F38181",
    "accent_3": "#F38181",
}

METRICS = [
    ("final_score", "Final Score", False),
    ("completed_tasks", "Completed Tasks", False),
    ("expired_tasks", "Expired Tasks", True),
    ("total_distance", "Total Distance", True),
]

plt.rcParams.update(
    {
        "font.family": "serif",
        "font.serif": ["Times New Roman", "Times", "Nimbus Roman", "DejaVu Serif"],
        "mathtext.fontset": "stix",
        "font.size": 9.5,
        "axes.titlesize": 10.5,
        "axes.labelsize": 10,
        "xtick.labelsize": 9.5,
        "ytick.labelsize": 9.5,
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
    rows: list[dict[str, str]] = []
    with step_csv.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        raise ValueError(f"Empty step log: {step_csv}")

    last = rows[-1]
    return {
        "final_score": float(last["total_score"]),
        "completed_tasks": float(last["completed_tasks"]),
        "expired_tasks": float(last["expired_tasks"]),
    }


def _read_total_distance(vehicle_csv: Path) -> float:
    per_vehicle_max: dict[str, float] = {}
    with vehicle_csv.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            vehicle_id = row["vehicle_id"]
            total_distance = float(row["total_distance"])
            previous = per_vehicle_max.get(vehicle_id)
            if previous is None or total_distance > previous:
                per_vehicle_max[vehicle_id] = total_distance
    if not per_vehicle_max:
        raise ValueError(f"Empty vehicle log: {vehicle_csv}")
    return float(sum(per_vehicle_max.values()))


def collect_baseline_metrics() -> dict[str, dict[str, dict[str, list[float]]]]:
    data: dict[str, dict[str, dict[str, list[float]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )

    for scale in SCALES:
        for scheduler in SCHEDULERS:
            pattern = f"{scale}_{scheduler}_seed*"
            for run_dir in BASELINES_DIR.glob(pattern):
                inner_dir = run_dir / f"{scale}_{scheduler}"
                step_csv = inner_dir / "step_log.csv"
                vehicle_csv = inner_dir / "vehicle_log.csv"
                if not step_csv.exists() or not vehicle_csv.exists():
                    continue

                summary = _read_step_summary(step_csv)
                summary["total_distance"] = _read_total_distance(vehicle_csv)

                for metric_name, _, _ in METRICS:
                    data[scale][scheduler][metric_name].append(summary[metric_name])

    return data


def summarize(data: dict[str, dict[str, dict[str, list[float]]]]) -> dict[str, dict[str, dict[str, tuple[float, float]]]]:
    summary: dict[str, dict[str, dict[str, tuple[float, float]]]] = defaultdict(dict)
    for scale in SCALES:
        for scheduler in SCHEDULERS:
            metric_summary: dict[str, tuple[float, float]] = {}
            metrics = data.get(scale, {}).get(scheduler, {})
            for metric_name, _, _ in METRICS:
                values = metrics.get(metric_name, [])
                if not values:
                    raise ValueError(
                        f"Missing values for scale={scale}, scheduler={scheduler}, metric={metric_name}"
                    )
                metric_summary[metric_name] = (mean(values), _safe_stdev(values))
            summary[scale][scheduler] = metric_summary
    return summary


def _beautify_axis(ax: plt.Axes) -> None:
    ax.set_axisbelow(True)
    ax.grid(axis="y", linestyle="--", linewidth=0.8, alpha=0.28)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_alpha(0.35)
    ax.spines["bottom"].set_alpha(0.35)


def plot_figure(summary: dict[str, dict[str, dict[str, tuple[float, float]]]]) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    fig = plt.figure(figsize=(7.6, 5.8))
    grid = fig.add_gridspec(2, 2)
    axes: dict[str, plt.Axes | tuple[plt.Axes, plt.Axes]] = {
        "final_score": fig.add_subplot(grid[0, 0]),
        "completed_tasks": fig.add_subplot(grid[0, 1]),
        "total_distance": fig.add_subplot(grid[1, 1]),
    }
    expired_grid = grid[1, 0].subgridspec(2, 1, height_ratios=[3.0, 1.25], hspace=0.06)
    expired_top = fig.add_subplot(expired_grid[0])
    expired_bottom = fig.add_subplot(expired_grid[1], sharex=expired_top)
    axes["expired_tasks"] = (expired_top, expired_bottom)

    x = np.arange(len(SCALES))
    width = 0.21
    offsets = [-width, 0.0, width]

    for metric_name, metric_label, lower_is_better in METRICS:
        values_by_scheduler: list[list[float]] = []
        for scheduler in SCHEDULERS:
            means = [summary[scale][scheduler][metric_name][0] for scale in SCALES]
            values_by_scheduler.append(means)

        best_scheduler_per_scale: list[str] = []
        for scale in SCALES:
            scores = {
                scheduler: summary[scale][scheduler][metric_name][0] for scheduler in SCHEDULERS
            }
            if lower_is_better:
                best_scheduler_per_scale.append(min(scores, key=scores.get))
            else:
                best_scheduler_per_scale.append(max(scores, key=scores.get))

        metric_axes = axes[metric_name]
        draw_axes = metric_axes if isinstance(metric_axes, tuple) else (metric_axes,)
        for ax in draw_axes:
            for idx, scheduler in enumerate(SCHEDULERS):
                means = values_by_scheduler[idx]
                colors = []
                for scale_idx, _ in enumerate(SCALES):
                    if best_scheduler_per_scale[scale_idx] == scheduler:
                        colors.append(PALETTE["accent_1"])
                    else:
                        colors.append(PALETTE[scheduler])

                ax.bar(
                    x + offsets[idx],
                    means,
                    width,
                    label=SCHEDULER_LABELS[scheduler],
                    color=colors,
                    edgecolor="none",
                    linewidth=0,
                    zorder=3,
                )

            ax.set_xticks(x)
            ax.set_xticklabels(["Small", "Medium", "Large"])
            ax.set_ylabel(metric_label)
            _beautify_axis(ax)

        if metric_name == "expired_tasks":
            all_values = [value for scheduler_values in values_by_scheduler for value in scheduler_values]
            upper_max = max(all_values) * 1.08
            expired_top.set_ylim(25, upper_max)
            expired_bottom.set_ylim(0, 3)
            expired_top.spines["bottom"].set_visible(False)
            expired_bottom.spines["top"].set_visible(False)
            expired_top.tick_params(axis="x", which="both", bottom=False, labelbottom=False)
            expired_bottom.set_xlabel("Scale")
            expired_bottom.set_ylabel("")
            expired_top.set_yticks([50, 100, 150, 200])
            expired_bottom.set_yticks([0, 1, 2, 3])

            break_size = 0.012
            break_kwargs = dict(color="#555555", clip_on=False, linewidth=0.9)
            expired_top.plot(
                (-break_size, +break_size),
                (-break_size, +break_size),
                transform=expired_top.transAxes,
                **break_kwargs,
            )
            expired_top.plot(
                (1 - break_size, 1 + break_size),
                (-break_size, +break_size),
                transform=expired_top.transAxes,
                **break_kwargs,
            )
            expired_bottom.plot(
                (-break_size, +break_size),
                (1 - break_size, 1 + break_size),
                transform=expired_bottom.transAxes,
                **break_kwargs,
            )
            expired_bottom.plot(
                (1 - break_size, 1 + break_size),
                (1 - break_size, 1 + break_size),
                transform=expired_bottom.transAxes,
                **break_kwargs,
            )
        else:
            draw_axes[0].set_xlabel("Scale")

    legend_axis = axes["final_score"]
    assert not isinstance(legend_axis, tuple)
    handles, labels = legend_axis.get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="upper center",
        ncol=3,
        frameon=False,
        bbox_to_anchor=(0.5, 0.985),
        columnspacing=1.8,
        handlelength=1.8,
        handletextpad=0.6,
        borderaxespad=0.2,
    )
    fig.subplots_adjust(left=0.1, right=0.995, bottom=0.12, top=0.90, wspace=0.34, hspace=0.34)

    fig.savefig(OUTPUT_PATH, bbox_inches="tight", pad_inches=0.02)
    return OUTPUT_PATH


def main() -> None:
    if not BASELINES_DIR.exists():
        raise FileNotFoundError(f"Baseline directory not found: {BASELINES_DIR}")

    data = collect_baseline_metrics()
    summary = summarize(data)
    output_path = plot_figure(summary)
    print(f"Saved Figure 1 to: {output_path}")


if __name__ == "__main__":
    main()
