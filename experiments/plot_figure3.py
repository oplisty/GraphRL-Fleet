from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
QLEARNING_DIR = ROOT / "experiments" / "qlearning"
OUTPUT_DIR = ROOT / "experiments" / "figures" / "main"
OUTPUT_PATH = OUTPUT_DIR / "fig_qlearning_training_curves.pdf"

MODELS = ["small", "medium", "mixed"]
MODEL_LABELS = {
    "small": "Small",
    "medium": "Medium",
    "mixed": "Mixed",
}
PALETTE = {
    "small": "#95E1D3",
    "medium": "#F38181",
    "mixed": "#FCE38A",
    "small_dark": "#95E1D3",
    "medium_dark": "#F38181",
    "mixed_dark": "#FCE38A",
}
ROLLING_WINDOW = 10

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


def read_history(model_name: str) -> dict[str, np.ndarray]:
    history_path = QLEARNING_DIR / model_name / "train_history.csv"
    if not history_path.exists():
        raise FileNotFoundError(f"Missing train history: {history_path}")

    episodes: list[float] = []
    total_rewards: list[float] = []
    eval_scores: list[float] = []

    with history_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            episodes.append(float(row["episode"]))
            total_rewards.append(float(row["total_reward"]))
            eval_scores.append(float(row["eval_score_mean"]))

    if not episodes:
        raise ValueError(f"Empty training history: {history_path}")

    return {
        "episode": np.asarray(episodes, dtype=float),
        "total_reward": np.asarray(total_rewards, dtype=float),
        "eval_score_mean": np.asarray(eval_scores, dtype=float),
    }


def rolling_mean(values: np.ndarray, window: int) -> np.ndarray:
    if len(values) < window:
        return values.copy()
    kernel = np.ones(window, dtype=float) / float(window)
    valid = np.convolve(values, kernel, mode="valid")
    prefix = np.full(window - 1, np.nan)
    return np.concatenate([prefix, valid])


def _beautify_axis(ax: plt.Axes) -> None:
    ax.set_axisbelow(True)
    ax.grid(axis="y", linestyle="-", linewidth=0.7, alpha=0.18)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_alpha(0.22)
    ax.spines["bottom"].set_alpha(0.22)


def plot_figure(histories: dict[str, dict[str, np.ndarray]]) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(2, 1, figsize=(9.2, 5.8), constrained_layout=True, sharex=True)

    metric_specs = [
        ("total_reward", "Total Reward", axes[0]),
        ("eval_score_mean", "Eval Score Mean", axes[1]),
    ]

    for metric_name, metric_label, ax in metric_specs:
        for model_name in MODELS:
            history = histories[model_name]
            episodes = history["episode"]
            raw_values = history[metric_name]
            smooth_values = rolling_mean(raw_values, ROLLING_WINDOW)

            dark_color = PALETTE[f"{model_name}_dark"]

            ax.plot(
                episodes,
                smooth_values,
                color=dark_color,
                linewidth=2.35,
                label=MODEL_LABELS[model_name],
                solid_capstyle="round",
                zorder=3,
            )
            ax.scatter(
                episodes[-1],
                smooth_values[-1],
                s=34,
                color=dark_color,
                edgecolor="#3A3A3A",
                linewidth=0.55,
                zorder=4,
            )

        ax.set_ylabel(metric_label)
        ax.margins(x=0.01)
        _beautify_axis(ax)

    axes[1].set_xlabel("Episode")

    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=3, frameon=False, bbox_to_anchor=(0.5, 1.02))

    fig.savefig(OUTPUT_PATH, bbox_inches="tight")
    return OUTPUT_PATH


def main() -> None:
    histories = {model_name: read_history(model_name) for model_name in MODELS}
    output_path = plot_figure(histories)
    print(f"Saved Figure 3 to: {output_path}")


if __name__ == "__main__":
    main()
