"""The results page's three charts (SPEC 2.10, Chunk 10).

Each chart is drawn from one table only, and the rows it draws are saved beside it as a
CSV, so the recompute check can rebuild them from `every-run.csv`. Colors are the
dataviz skill's reference palette: models take categorical slots 1-3 in table order; the
consistency chart uses the status colors, each named in the legend.
"""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # files only, never a window
import matplotlib.pyplot as plt  # noqa: E402

SURFACE = "#ffffff"  # GitHub shows the picture on white or dark; white reads on both
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
SERIES = ("#2a78d6", "#eb6834", "#1baf7a")  # slots 1-3: blue, orange, aqua
GOOD, WARNING, CRITICAL = "#0ca30c", "#fab219", "#d03b3b"

BAR = 0.5  # bar thickness as a share of its row
DPI = 200

PASS_RATE = "pass-rate-by-model"
CONSISTENCY = "consistency-by-model"
FAILURES = "failures-by-label"
CHARTS = (PASS_RATE, CONSISTENCY, FAILURES)

PASS_RATE_COLUMNS = (
    "model",
    "passed",
    "replies_graded",
    "pass_rate_percent",
    "range_low_percent",
    "range_high_percent",
)


def chart_data(tables: dict[str, list[dict]], pooled: str) -> dict[str, list[dict]]:
    """The rows each chart draws, taken from the tables. `pooled` is the all-models row."""
    return {
        PASS_RATE: [
            {c: r[c] for c in PASS_RATE_COLUMNS}
            for r in tables[PASS_RATE]
            if r["model"] != pooled and r["pass_rate_percent"]
        ],
        CONSISTENCY: [dict(r) for r in tables[CONSISTENCY] if r["same_answer_every_run_percent"]],
        FAILURES: [dict(r) for r in tables[FAILURES]],
    }


# --- drawing -------------------------------------------------------------------------


def _axes(rows: int, width: float = 8.0):
    fig, ax = plt.subplots(figsize=(width, 1.3 + 0.55 * rows), dpi=DPI)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(BASELINE)
    ax.tick_params(colors=MUTED, length=0, labelsize=9)
    ax.tick_params(axis="y", colors=INK, labelsize=10)
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    return fig, ax


def _title(ax, text: str) -> None:
    ax.set_title(text, loc="left", color=INK, fontsize=11, pad=12)


def _save(fig, path: Path) -> None:
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE, metadata={"Software": None})
    plt.close(fig)


def _pass_rate(rows: list[dict], path: Path) -> None:
    fig, ax = _axes(len(rows))
    ys = list(range(len(rows)))[::-1]  # first row on top
    for y, r in zip(ys, rows, strict=True):
        low, rate, high = (
            int(r[k]) for k in ("range_low_percent", "pass_rate_percent", "range_high_percent")
        )
        ax.plot(
            [low, high], [y, y], color=SERIES[0], linewidth=2, solid_capstyle="round",
            clip_on=False,
        )  # fmt: skip
        ax.plot(
            rate, y, "o", markersize=9, color=SERIES[0], markeredgecolor=SURFACE,
            markeredgewidth=2, clip_on=False,
        )  # fmt: skip
        ax.annotate(
            f"{r['passed']} of {r['replies_graded']} ({rate}%)",
            (rate, y),
            xytext=(0, 9),
            textcoords="offset points",
            ha="center",
            color=INK_2,
            fontsize=9,
        )
    ax.set_yticks(ys, [r["model"] for r in rows])
    ax.set_ylim(-0.6, len(rows) - 0.3)
    ax.set_xlim(0, 100)
    ax.set_xticks(range(0, 101, 20), [f"{x}%" for x in range(0, 101, 20)])
    _title(ax, "Drawings passed by each model (run 1), with the 95% range")
    _save(fig, path)


def _text_on(fill: str) -> str:
    """White or ink, whichever reads on this fill."""
    r, g, b = (int(fill[i : i + 2], 16) / 255 for i in (1, 3, 5))
    return INK if 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.5 else SURFACE


def _consistency(rows: list[dict], path: Path) -> None:
    fig, ax = _axes(len(rows))
    ys = list(range(len(rows)))[::-1]
    parts = (("always_passed", "Passed every run", GOOD), ("mixed", "Mixed", WARNING))
    parts += (("always_failed", "Failed every run", CRITICAL),)
    most = max((int(r["drawings_run_more_than_once"]) for r in rows), default=0)
    for column, name, color in parts:
        for y, r in zip(ys, rows, strict=True):
            left = sum(int(r[c]) for c, _, _ in parts[: [p[0] for p in parts].index(column)])
            n = int(r[column])
            ax.barh(
                y, n, left=left, height=BAR, color=color, edgecolor=SURFACE, linewidth=2,
                label=name if y == ys[0] else None,
            )  # fmt: skip
            if n and n / max(most, 1) > 0.02:
                ax.text(
                    left + n / 2, y, str(n), ha="center", va="center",
                    color=_text_on(color), fontsize=9,
                )  # fmt: skip
    ax.set_yticks(ys, [r["model"] for r in rows])
    ax.set_xlim(0, max(most, 1))
    ax.set_xlabel("Drawings run more than once", color=MUTED, fontsize=9)
    ax.legend(
        loc="lower left", bbox_to_anchor=(0, 1.0), ncol=3, frameon=False, fontsize=9,
        labelcolor=INK_2, handlelength=1, borderaxespad=0.2,
    )  # fmt: skip
    ax.set_title(
        "Did each model give the same verdict on every run?",
        loc="left", color=INK, fontsize=11, pad=30,
    )  # fmt: skip
    _save(fig, path)


def _failures(rows: list[dict], path: Path) -> None:
    """One stacked bar per label, a segment per model, largest total on top."""
    models = [c for c in (rows[0] if rows else {}) if c not in ("label", "total")]
    rows = sorted(rows, key=lambda r: -int(r["total"]))
    fig, ax = _axes(len(rows))
    ys = list(range(len(rows)))[::-1]
    most = max((int(r["total"]) for r in rows), default=0)
    for i, model in enumerate(models):
        color = SERIES[i % len(SERIES)]
        for y, r in zip(ys, rows, strict=True):
            left = sum(int(r[m]) for m in models[:i])
            n = int(r[model])
            ax.barh(
                y, n, left=left, height=BAR, color=color, edgecolor=SURFACE, linewidth=2,
                label=model if y == ys[0] else None,
            )  # fmt: skip
    for y, r in zip(ys, rows, strict=True):
        ax.text(int(r["total"]) + most * 0.015, y, r["total"], va="center", color=INK_2, fontsize=9)
    ax.set_yticks(ys, [r["label"] for r in rows])
    ax.set_xlim(0, max(most, 1) * 1.08)
    ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
    ax.set_xlabel("Missed sizes in run 1", color=MUTED, fontsize=9)
    if models:
        ax.legend(
            loc="lower left", bbox_to_anchor=(0, 1.0), ncol=len(models), frameon=False,
            fontsize=9, labelcolor=INK_2, handlelength=1, borderaxespad=0.2,
        )  # fmt: skip
    ax.set_title(
        "Missed sizes by failure label (run 1)",
        loc="left", color=INK, fontsize=11, pad=30,
    )  # fmt: skip
    _save(fig, path)


DRAW = {PASS_RATE: _pass_rate, CONSISTENCY: _consistency, FAILURES: _failures}


def write(out: Path, data: dict[str, list[dict]]) -> None:
    """charts/<name>.png and charts/<name>.csv for each chart."""
    folder = out / "charts"
    folder.mkdir(parents=True, exist_ok=True)
    for name in CHARTS:
        rows = data[name]
        if rows:
            with (folder / f"{name}.csv").open("w", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            DRAW[name](rows, folder / f"{name}.png")
