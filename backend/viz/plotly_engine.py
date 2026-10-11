import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from typing import Dict
from backend.schemas import ChartSpec, ToolResult
from backend.dataset import DatasetContext

MODERN_PALETTE = [
    "#6366F1",  # Indigo
    "#38BDF8",  # Sky
    "#A855F7",  # Purple
    "#34D399",  # Emerald
    "#F472B6",  # Pink
    "#FBBF24",  # Amber
    "#FB7185",  # Rose
    "#2DD4BF",  # Teal
]


def _prettify_label(name: str) -> str:
    if not name or not isinstance(name, str):
        return ""
    return name.replace("_", " ").strip().title()


def render_plotly(spec: ChartSpec, ctx: DatasetContext, tool_results: Dict[str, ToolResult] = None, theme: str = "dark"):
    tool_results = tool_results or {}
    tr = None
    is_light = (theme == "light")

    if spec.source == "tool_result" and spec.tool_result_id in tool_results:
        tr = tool_results[spec.tool_result_id]
        if spec.chart_type == "heatmap" and "matrix" in (tr.chart_data or {}):
            df = pd.DataFrame(tr.chart_data["matrix"])
        else:
            df = pd.DataFrame(tr.chart_data)
    else:
        df = ctx.df.copy()

    # Sample large raw datasets for scatter/box
    if len(df) > 2500 and spec.chart_type in ["scatter", "box"]:
        df = df.sample(2500, random_state=42)

    # Smart aggregation & top-N capping for bar charts so they stay compact and readable
    if spec.chart_type == "bar":
        max_bars = min(spec.top_n or 10, 12)
        if not spec.x or spec.x not in df.columns:
            df = df.head(max_bars).copy()
            df["_record_label"] = [f"Row {i + 1}" for i in range(len(df))]
            spec = spec.model_copy(update={"x": "_record_label"})
        elif spec.source == "dataset" and (len(df) > max_bars or df[spec.x].duplicated().any()):
            if isinstance(spec.y, str) and spec.y in df.columns and spec.y != spec.x and pd.api.types.is_numeric_dtype(df[spec.y]):
                agg_fn = spec.aggregation if spec.aggregation in ("sum", "mean", "median", "min", "max") else "mean"
                df = (
                    getattr(df.groupby(spec.x, dropna=False)[spec.y], agg_fn)()
                    .reset_index()
                    .sort_values(by=spec.y, ascending=False)
                    .head(max_bars)
                )
            else:
                count_col = "Count"
                df = (
                    df[spec.x]
                    .value_counts(dropna=False)
                    .head(max_bars)
                    .reset_index()
                )
                df.columns = [spec.x, count_col]
                spec = spec.model_copy(update={"y": count_col})
        elif len(df) > max_bars:
            df = df.head(max_bars)

    fig = None

    labels = {}
    if spec.x:
        labels[spec.x] = spec.x_label or ("Record" if spec.x == "_record_label" else _prettify_label(spec.x))
    if isinstance(spec.y, str):
        labels[spec.y] = spec.y_label or _prettify_label(spec.y)

    if spec.chart_type == "bar":
        barmode = "stack" if spec.stacked else "group"
        if isinstance(spec.y, list):
            fig = px.bar(
                df, x=spec.x, y=spec.y, title=spec.title, barmode=barmode,
                orientation=spec.orientation, labels=labels,
                color_discrete_sequence=MODERN_PALETTE
            )
        else:
            if spec.orientation == "h":
                fig = px.bar(
                    df, y=spec.x, x=spec.y, color=spec.color, title=spec.title,
                    barmode=barmode, orientation="h", labels=labels,
                    color_discrete_sequence=MODERN_PALETTE
                )
            else:
                fig = px.bar(
                    df, x=spec.x, y=spec.y, color=spec.color, title=spec.title,
                    barmode=barmode, orientation="v", labels=labels,
                    color_discrete_sequence=MODERN_PALETTE
                )
        try:
            fig.update_traces(marker_line_width=0, opacity=0.92, marker_cornerradius=6)
        except Exception:
            fig.update_traces(marker_line_width=0, opacity=0.92)

    elif spec.chart_type == "line":
        if spec.x and spec.x in df.columns:
            df = df.sort_values(by=spec.x)
        fig = px.line(
            df, x=spec.x, y=spec.y, color=spec.color, title=spec.title,
            markers=True, labels=labels, color_discrete_sequence=MODERN_PALETTE
        )
        fig.update_traces(line=dict(width=2.5), marker=dict(size=6))

    elif spec.chart_type == "histogram":
        fig = px.histogram(
            df, x=spec.x, color=spec.color, title=spec.title,
            nbins=spec.bins or 20, labels=labels, color_discrete_sequence=MODERN_PALETTE
        )
        fig.update_traces(marker_line_width=0.5, marker_line_color="rgba(255,255,255,0.15)", opacity=0.88)

    elif spec.chart_type == "scatter":
        fig = px.scatter(
            df, x=spec.x, y=spec.y, color=spec.color, title=spec.title,
            labels=labels, color_discrete_sequence=MODERN_PALETTE
        )
        fig.update_traces(marker=dict(size=7, opacity=0.8, line=dict(width=0.5, color="rgba(255,255,255,0.2)")))

    elif spec.chart_type == "box":
        fig = px.box(
            df, x=spec.x, y=spec.y, color=spec.color, title=spec.title,
            labels=labels, color_discrete_sequence=MODERN_PALETTE
        )

    elif spec.chart_type == "pie":
        pie_df = df.copy()
        if spec.x and spec.x in pie_df.columns:
            if isinstance(spec.y, str) and spec.y in pie_df.columns and pd.api.types.is_numeric_dtype(pie_df[spec.y]):
                pie_df = (
                    pie_df.groupby(spec.x, dropna=False)[spec.y]
                    .sum()
                    .reset_index()
                    .sort_values(by=spec.y, ascending=False)
                    .head(10)
                )
                fig = px.pie(
                    pie_df, names=spec.x, values=spec.y, title=spec.title,
                    hole=0.35, color_discrete_sequence=MODERN_PALETTE
                )
            else:
                vc = pie_df[spec.x].value_counts(dropna=False).head(10).reset_index()
                vc.columns = [spec.x, "Count"]
                fig = px.pie(
                    vc, names=spec.x, values="Count", title=spec.title,
                    hole=0.35, color_discrete_sequence=MODERN_PALETTE
                )

    elif spec.chart_type == "heatmap":
        if tr and "matrix" in (tr.chart_data or {}):
            fig = px.imshow(
                df, title=spec.title, text_auto=".2f", aspect="auto",
                color_continuous_scale="Tealrose"
            )
        else:
            num_df = df.select_dtypes(include="number")
            corr_df = num_df.corr() if num_df.shape[1] >= 2 else df
            fig = px.imshow(
                corr_df, title=spec.title, text_auto=".2f", aspect="auto",
                color_continuous_scale="Tealrose"
            )

    if fig:
        chart_height = 260 if spec.chart_type not in ("heatmap", "pie") else 290
        paper_bg = "rgba(255, 255, 255, 0.92)" if is_light else "rgba(15, 23, 42, 0.65)"
        title_col = "#0F172A" if is_light else "#F8FAFC"
        text_col = "#334155" if is_light else "#CBD5E1"
        tick_col = "#64748B" if is_light else "#94A3B8"
        grid_col = "rgba(15, 23, 42, 0.07)" if is_light else "rgba(255, 255, 255, 0.06)"
        hover_bg = "#FFFFFF" if is_light else "#0F172A"
        hover_border = "rgba(15, 23, 42, 0.15)" if is_light else "rgba(255, 255, 255, 0.15)"

        fig.update_layout(
            template="plotly_white" if is_light else "plotly_dark",
            height=chart_height,
            autosize=True,
            paper_bgcolor=paper_bg,
            plot_bgcolor="rgba(0, 0, 0, 0)",
            font=dict(family="Plus Jakarta Sans, Inter, system-ui, sans-serif", size=11, color=text_col),
            title=dict(
                text=spec.title,
                font=dict(family="Plus Jakarta Sans, Inter, system-ui, sans-serif", size=13, color=title_col),
                x=0.02,
                y=0.94,
            ),
            margin=dict(l=42, r=20, t=42, b=36),
            bargap=0.32,
            xaxis=dict(
                showgrid=False,
                zeroline=False,
                showline=False,
                tickfont=dict(size=10, color=tick_col),
                title_font=dict(size=11, color=text_col),
            ),
            yaxis=dict(
                showgrid=True,
                gridcolor=grid_col,
                gridwidth=1,
                zeroline=False,
                showline=False,
                tickfont=dict(size=10, color=tick_col),
                title_font=dict(size=11, color=text_col),
            ),
            hoverlabel=dict(
                bgcolor=hover_bg,
                bordercolor=hover_border,
                font=dict(family="Plus Jakarta Sans, Inter, system-ui, sans-serif", size=11, color=title_col),
            ),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=-0.28,
                xanchor="center",
                x=0.5,
                font=dict(size=10, color=text_col),
                bgcolor="rgba(0,0,0,0)",
            ),
        )

    return fig

