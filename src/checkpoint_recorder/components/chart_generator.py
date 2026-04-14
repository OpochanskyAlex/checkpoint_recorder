"""
Chart Generator — FR-14: time-series chart rendering.

Produces an in-memory PNG bytes object from Entry history.
Uses the Agg (non-GUI) matplotlib backend — safe in server environments.
"""
import io
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates


def render_chart(
    metric_name: str,
    unit: str | None,
    dimension_names: list[str] | None,
    entries: list[tuple[datetime, float | None, dict | None]],
) -> bytes:
    """
    Render a time-series PNG chart and return raw bytes.

    entries: list of (entry_timestamp, value, dimension_assignments)
    Raises ValueError if entries is empty (AC-FR14-4).
    """
    if not entries:
        raise ValueError("No entries to chart.")

    fig, ax = plt.subplots(figsize=(10, 4))
    fig.patch.set_facecolor("#f9f9f9")
    ax.set_facecolor("#f9f9f9")

    ylabel = metric_name
    if unit:
        ylabel = f"{metric_name} ({unit})"

    is_compound = bool(dimension_names)

    if is_compound:
        # Plot each dimension as a separate line
        dim_data: dict[str, list[tuple[datetime, float]]] = {d: [] for d in dimension_names}
        for ts, _val, assignments in entries:
            if assignments:
                for dim, v in assignments.items():
                    if dim in dim_data and v is not None:
                        dim_data[dim].append((ts, float(v)))

        plotted = False
        for dim, points in dim_data.items():
            if points:
                xs = [p[0] for p in points]
                ys = [p[1] for p in points]
                ax.plot(xs, ys, marker="o", markersize=4, linewidth=1.5, label=dim)
                plotted = True
        if plotted:
            ax.legend(fontsize=8)
        else:
            raise ValueError("No plottable dimension data in entries.")
    else:
        # Single-value metric
        points = [
            (ts, float(val))
            for ts, val, _ in entries
            if val is not None
        ]
        if not points:
            raise ValueError("No numeric values to chart.")
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        ax.plot(xs, ys, marker="o", markersize=4, linewidth=1.5, color="#4a90d9")
        ax.fill_between(xs, ys, alpha=0.08, color="#4a90d9")

    # Formatting
    ax.set_title(metric_name, fontsize=13, fontweight="bold", pad=10)
    ax.set_ylabel(ylabel, fontsize=10)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    fig.autofmt_xdate(rotation=30, ha="right")
    ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.6)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120)
    plt.close(fig)
    buf.seek(0)
    return buf.read()
