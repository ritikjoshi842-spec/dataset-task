import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import io
from typing import Dict
from backend.schemas import ChartSpec, ToolResult
from backend.dataset import DatasetContext

def render_mpl(spec: ChartSpec, ctx: DatasetContext, tool_results: Dict[str, ToolResult] = None) -> bytes:
    tool_results = tool_results or {}
    
    if spec.source == "tool_result" and spec.tool_result_id in tool_results:
        tr = tool_results[spec.tool_result_id]
        if spec.chart_type == "heatmap" and "matrix" in tr.chart_data:
            df = pd.DataFrame(tr.chart_data["matrix"])
        else:
            df = pd.DataFrame(tr.chart_data)
    else:
        df = ctx.df.copy()
        
    if len(df) > 5000 and spec.chart_type in ["scatter", "box"]:
        df = df.sample(5000, random_state=42)
        
    fig, ax = plt.subplots(figsize=(6.8, 3.8), dpi=160)
    sns.set_theme(style="whitegrid")
    palette = ["#38BDF8", "#818CF8", "#34D399", "#F472B6", "#FBBF24", "#A78BFA"]
    
    try:
        if spec.chart_type == "bar":
            df_bar = df.copy()
            if not spec.x or spec.x not in df_bar.columns:
                df_bar = df_bar.head(12).copy()
                df_bar["_record_label"] = [f"Row {i + 1}" for i in range(len(df_bar))]
                spec = spec.model_copy(update={"x": "_record_label"})
            elif spec.source == "dataset" and (len(df_bar) > 12 or df_bar[spec.x].duplicated().any()):
                if isinstance(spec.y, str) and spec.y in df_bar.columns and spec.y != spec.x and pd.api.types.is_numeric_dtype(df_bar[spec.y]):
                    agg_fn = spec.aggregation if spec.aggregation in ("sum", "mean", "median", "min", "max") else "mean"
                    df_bar = (
                        getattr(df_bar.groupby(spec.x, dropna=False)[spec.y], agg_fn)()
                        .reset_index()
                        .sort_values(by=spec.y, ascending=False)
                        .head(12)
                    )
                else:
                    vc = df_bar[spec.x].value_counts(dropna=False).head(12).reset_index()
                    vc.columns = [spec.x, "Count"]
                    df_bar = vc
                    spec = spec.model_copy(update={"y": "Count"})
            else:
                df_bar = df_bar.head(12).copy()

            if spec.x in df_bar.columns:
                df_bar[spec.x] = df_bar[spec.x].astype(str)
            if isinstance(spec.y, list):
                df_bar.set_index(spec.x)[spec.y].plot(
                    kind="bar" if spec.orientation=="v" else "barh",
                    ax=ax,
                    stacked=spec.stacked,
                    color=palette[:len(spec.y)]
                )
            else:
                if spec.orientation == 'h':
                    sns.barplot(data=df_bar, y=spec.x, x=spec.y, hue=spec.color, ax=ax, color="#38BDF8")
                else:
                    sns.barplot(data=df_bar, x=spec.x, y=spec.y, hue=spec.color, ax=ax, color="#38BDF8")
                    if len(df_bar) > 5:
                        plt.xticks(rotation=30, ha='right', fontsize=8.5)
                    
        elif spec.chart_type == "line":
            if spec.x and spec.x in df.columns:
                df = df.sort_values(by=spec.x)
            if isinstance(spec.y, list):
                for idx, y_col in enumerate(spec.y):
                    sns.lineplot(data=df, x=spec.x, y=y_col, ax=ax, label=y_col, marker="o", color=palette[idx % len(palette)])
            else:
                sns.lineplot(data=df, x=spec.x, y=spec.y, hue=spec.color, ax=ax, marker="o", color="#38BDF8")
                
        elif spec.chart_type == "histogram":
            sns.histplot(data=df, x=spec.x, hue=spec.color, bins=spec.bins or 'auto', multiple="stack", ax=ax, color="#38BDF8")
            
        elif spec.chart_type == "scatter":
            sns.scatterplot(data=df, x=spec.x, y=spec.y, hue=spec.color, ax=ax, color="#38BDF8", alpha=0.75)
            
        elif spec.chart_type == "box":
            sns.boxplot(data=df, x=spec.x, y=spec.y, hue=spec.color, ax=ax, color="#38BDF8")

        elif spec.chart_type == "pie":
            pie_df = df.copy()
            if spec.x and spec.x in pie_df.columns:
                if isinstance(spec.y, str) and spec.y in pie_df.columns and pd.api.types.is_numeric_dtype(pie_df[spec.y]):
                    pie_df = pie_df.groupby(spec.x, dropna=False)[spec.y].sum().reset_index().sort_values(by=spec.y, ascending=False).head(8)
                    ax.pie(pie_df[spec.y], labels=pie_df[spec.x].astype(str), autopct="%1.1f%%", colors=palette)
                else:
                    vc = pie_df[spec.x].value_counts(dropna=False).head(8)
                    ax.pie(vc.values, labels=vc.index.astype(str), autopct="%1.1f%%", colors=palette)
            
        elif spec.chart_type == "heatmap":
            corr_df = df if (spec.source == "tool_result" and spec.tool_result_id in tool_results) else df.select_dtypes(include="number").corr()
            sns.heatmap(corr_df, annot=True, cmap="coolwarm", center=0, fmt=".2f", ax=ax)
            
        ax.set_title(spec.title, fontsize=11, fontweight="bold", pad=10)
        if spec.x_label: ax.set_xlabel(spec.x_label, fontsize=9)
        if spec.y_label and isinstance(spec.y, str): ax.set_ylabel(spec.y_label, fontsize=9)
        sns.despine(top=True, right=True)
        
        plt.tight_layout()
        
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        buf.seek(0)
        return buf.read()
    finally:
        plt.close(fig)
