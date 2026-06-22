"""
tools/viz_tools.py
─────────────────────────────────────────────────────────────────────────────
Chart generation tools. All tools write files to the charts/ directory and
return the path — Deep Agents' FilesystemMiddleware can offload large chart
data to its virtual filesystem, and the agent can reference paths in follow-up
report-building steps.

Tools:
  chart_bar         – vertical bar chart (PNG)
  chart_line        – line / time-series chart (PNG)
  chart_scatter     – scatter with optional color grouping (PNG)
  chart_histogram   – histogram for a numeric column (PNG)
  chart_heatmap     – correlation heatmap (PNG)
  chart_interactive – interactive Plotly chart (self-contained HTML)
"""

from __future__ import annotations

import threading
import uuid
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from config.settings import settings
from tools.bigquery_tools import get_cached_df

sns.set_theme(style="whitegrid", palette="muted")

# TICKET-027: matplotlib's pyplot global state machine is not thread-safe.
# All five static-chart functions wrap their figure construction in this lock
# to prevent concurrent FastAPI requests from corrupting each other's figures.
# chart_interactive uses Plotly (stateless) and does NOT need this lock.
_plot_lock = threading.Lock()


def _require(key: str) -> pd.DataFrame:
    df = get_cached_df(key)
    if df is None:
        raise ValueError(f"No DataFrame under '{key}'. Run bq_run_query or sheet_from_url first.")
    return df


def _save(fig, prefix: str = "chart") -> str:
    path = settings.charts_dir / f"{prefix}_{uuid.uuid4().hex[:8]}.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return str(path)


def chart_bar(
    x_column: str,
    y_column: str,
    title: str = "",
    top_n: int = 20,
    cache_key: str = "latest",
) -> str:
    """
    Vertical bar chart.

    Args:
        x_column:  Categories / labels (x-axis).
        y_column:  Numeric values (bar heights).
        title:     Chart title (auto-generated if blank).
        top_n:     Show only the top N bars by y value (default 20).
        cache_key: DataFrame name (default 'latest').

    Returns:
        File path of the saved PNG.
    """
    df = _require(cache_key)
    # TICKET-012: validate column names before indexing to return a clear error
    # instead of an unhandled KeyError.
    missing = [c for c in [x_column, y_column] if c not in df.columns]
    if missing:
        return f"Columns not found: {missing}. Available: {list(df.columns)}"

    plot_df = df[[x_column, y_column]].sort_values(y_column, ascending=False).head(top_n)

    # TICKET-027: acquire the pyplot lock for the duration of figure construction.
    with _plot_lock:
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.bar(plot_df[x_column].astype(str), plot_df[y_column])
        ax.set_xlabel(x_column)
        ax.set_ylabel(y_column)
        ax.set_title(title or f"{y_column} by {x_column} (top {top_n})")
        plt.xticks(rotation=45, ha="right")
        plt.tight_layout()
        path = _save(fig, "bar")
    return f"Bar chart saved: {path}"


def chart_line(
    x_column: str,
    y_columns: str,
    title: str = "",
    cache_key: str = "latest",
) -> str:
    """
    Line chart — ideal for time-series or ordered data.

    Args:
        x_column:  X-axis column (dates or ordered labels).
        y_columns: Comma-separated numeric column(s), e.g. 'revenue,cost'.
        title:     Chart title.
        cache_key: DataFrame name (default 'latest').

    Returns:
        File path of the saved PNG.
    """
    df = _require(cache_key)
    cols = [c.strip() for c in y_columns.split(",")]
    missing = [c for c in cols if c not in df.columns]
    if missing:
        return f"Columns not found: {missing}. Available: {list(df.columns)}"

    # TICKET-028: errors="ignore" was removed from pd.to_datetime in pandas 3.0.
    try:
        x = pd.to_datetime(df[x_column])
    except (ValueError, TypeError):
        x = df[x_column]

    # TICKET-027: acquire the pyplot lock for the duration of figure construction.
    with _plot_lock:
        fig, ax = plt.subplots(figsize=(12, 5))
        for col in cols:
            ax.plot(x, df[col], marker="o", markersize=3, label=col)
        ax.set_xlabel(x_column)
        ax.set_title(title or f"{', '.join(cols)} over {x_column}")
        if len(cols) > 1:
            ax.legend()
        fig.autofmt_xdate()
        plt.tight_layout()
        path = _save(fig, "line")
    return f"Line chart saved: {path}"


def chart_scatter(
    x_column: str,
    y_column: str,
    color_column: str = "",
    title: str = "",
    cache_key: str = "latest",
) -> str:
    """
    Scatter plot with optional colour grouping.

    Args:
        x_column:     Numeric x-axis.
        y_column:     Numeric y-axis.
        color_column: Optional categorical column to colour points by.
        title:        Chart title.
        cache_key:    DataFrame name (default 'latest').
    """
    df = _require(cache_key)
    # TICKET-012: validate column names before indexing.
    missing = [c for c in [x_column, y_column] if c not in df.columns]
    if missing:
        return f"Columns not found: {missing}. Available: {list(df.columns)}"

    # TICKET-027: acquire the pyplot lock for the duration of figure construction.
    with _plot_lock:
        fig, ax = plt.subplots(figsize=(9, 6))
        if color_column and color_column in df.columns:
            cats = df[color_column].unique()
            palette = sns.color_palette("tab10", len(cats))
            for cat, colour in zip(cats, palette):
                mask = df[color_column] == cat
                ax.scatter(df.loc[mask, x_column], df.loc[mask, y_column],
                           label=str(cat), color=colour, alpha=0.6, s=20)
            ax.legend(title=color_column, fontsize=8)
        else:
            ax.scatter(df[x_column], df[y_column], alpha=0.5, s=15)
        ax.set_xlabel(x_column)
        ax.set_ylabel(y_column)
        ax.set_title(title or f"{y_column} vs {x_column}")
        plt.tight_layout()
        path = _save(fig, "scatter")
    return f"Scatter plot saved: {path}"


def chart_histogram(
    column: str,
    bins: int = 30,
    title: str = "",
    cache_key: str = "latest",
) -> str:
    """
    Histogram of a numeric column.

    Args:
        column:    Column to plot.
        bins:      Number of bins (default 30).
        title:     Chart title.
        cache_key: DataFrame name (default 'latest').
    """
    df = _require(cache_key)
    if column not in df.columns:
        return f"Column '{column}' not found. Available: {list(df.columns)}"

    # TICKET-027: acquire the pyplot lock for the duration of figure construction.
    with _plot_lock:
        fig, ax = plt.subplots(figsize=(9, 5))
        ax.hist(df[column].dropna(), bins=bins, edgecolor="white", linewidth=0.5)
        ax.set_xlabel(column)
        ax.set_ylabel("Count")
        ax.set_title(title or f"Distribution of {column}")
        plt.tight_layout()
        path = _save(fig, "histogram")
    return f"Histogram saved: {path}"


def chart_heatmap(
    cache_key: str = "latest",
    method: str = "pearson",
    title: str = "",
) -> str:
    """
    Correlation heatmap for all numeric columns.

    Args:
        cache_key: DataFrame name (default 'latest').
        method:    'pearson', 'spearman', or 'kendall'.
        title:     Chart title.
    """
    df = _require(cache_key)
    num = df.select_dtypes(include="number")
    if num.shape[1] < 2:
        return "Need ≥ 2 numeric columns."
    corr = num.corr(method=method)
    n = corr.shape[0]

    # TICKET-027: acquire the pyplot lock for the duration of figure construction.
    with _plot_lock:
        fig, ax = plt.subplots(figsize=(max(8, n), max(6, n - 1)))
        sns.heatmap(corr, annot=True, fmt=".2f", cmap="coolwarm", center=0, linewidths=0.5, ax=ax)
        ax.set_title(title or f"Correlation heatmap ({method})")
        plt.tight_layout()
        path = _save(fig, "heatmap")
    return f"Heatmap saved: {path}"


def chart_interactive(
    chart_type: str,
    x_column: str,
    y_column: str,
    color_column: str = "",
    title: str = "",
    cache_key: str = "latest",
) -> str:
    """
    Interactive Plotly chart saved as a self-contained HTML file.
    Great for sharing — recipients can hover, zoom, and filter without any installs.

    Args:
        chart_type:   'bar', 'line', 'scatter', 'area', 'box', or 'violin'.
        x_column:     X-axis column.
        y_column:     Y-axis column.
        color_column: Optional grouping / colour column.
        title:        Chart title.
        cache_key:    DataFrame name (default 'latest').

    Returns:
        File path of the saved HTML.
    """
    import plotly.express as px

    df = _require(cache_key)
    # TICKET-012: validate column names before passing to Plotly.
    missing = [c for c in [x_column, y_column] if c not in df.columns]
    if missing:
        return f"Columns not found: {missing}. Available: {list(df.columns)}"

    kwargs: dict = dict(data_frame=df, x=x_column, y=y_column,
                        title=title or f"{y_column} vs {x_column}")
    if color_column and color_column in df.columns:
        kwargs["color"] = color_column

    # TICKET-013: validate chart_type explicitly; never silently default to scatter.
    chart_fns = {
        "bar": px.bar, "line": px.line, "scatter": px.scatter,
        "area": px.area, "box": px.box, "violin": px.violin,
    }
    fn = chart_fns.get(chart_type.lower())
    if fn is None:
        return f"Unknown chart_type '{chart_type}'. Valid types: {list(chart_fns.keys())}"

    fig = fn(**kwargs)
    out = settings.charts_dir / f"interactive_{uuid.uuid4().hex[:8]}.html"
    fig.write_html(str(out), include_plotlyjs="cdn")
    return f"Interactive chart saved: {out}"
