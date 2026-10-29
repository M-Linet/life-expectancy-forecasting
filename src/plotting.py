"""Shared chart style. Fixed colour per region so it's the same in every chart."""

import matplotlib.pyplot as plt

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
GRID = "#e4e3df"

# Fixed categorical order (never cycled).
PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]

REGION_COLORS = {
    "Africa": PALETTE[0],
    "Americas": PALETTE[1],
    "Eastern Mediterranean": PALETTE[2],
    "Europe": PALETTE[3],
    "South-East Asia": PALETTE[4],
    "Western Pacific": PALETTE[5],
}

SEX_COLORS = {"female": PALETTE[0], "male": PALETTE[1], "both": INK_SECONDARY}

# Sequential single-hue ramp (light -> dark blue) for heatmaps.
SEQUENTIAL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]


def set_style() -> None:
    plt.rcParams.update({
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "figure.dpi": 110,
        "savefig.dpi": 160,
        "savefig.bbox": "tight",
        "font.size": 10,
        "axes.titlesize": 12,
        "axes.titleweight": "bold",
        "axes.titlelocation": "left",
        "axes.labelcolor": INK_SECONDARY,
        "axes.edgecolor": GRID,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.axisbelow": True,
        "grid.color": GRID,
        "grid.linewidth": 0.6,
        "xtick.color": INK_SECONDARY,
        "ytick.color": INK_SECONDARY,
        "text.color": INK,
        "lines.linewidth": 2,
        "legend.frameon": False,
    })


def stacked_contributions(ax, table, colors=None, height=0.62):
    """Horizontal stacked bars, positives right of zero and negatives left, tick at the net total."""
    import numpy as np

    colors = colors or PALETTE
    y = np.arange(len(table))
    pos_left = np.zeros(len(table))
    neg_left = np.zeros(len(table))
    for i, col in enumerate(table.columns):
        vals = table[col].to_numpy(dtype=float)
        pos, neg = np.where(vals > 0, vals, 0), np.where(vals < 0, vals, 0)
        ax.barh(y, pos, left=pos_left, color=colors[i % len(colors)], height=height,
                edgecolor=SURFACE, linewidth=1.5, label=col)
        ax.barh(y, neg, left=neg_left, color=colors[i % len(colors)], height=height,
                edgecolor=SURFACE, linewidth=1.5)
        pos_left += pos
        neg_left += neg
    net = table.sum(axis=1).to_numpy()
    ax.scatter(net, y, marker="|", s=260, color=INK, linewidths=2.2, zorder=4, label="Net change")
    ax.axvline(0, color=INK_SECONDARY, linewidth=0.8)
    ax.margins(x=0.05)
    ax.set_yticks(y, table.index)
    ax.grid(axis="y", visible=False)
    return ax
