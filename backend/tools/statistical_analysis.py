import pandas as pd
import numpy as np
from typing import List, Optional, Literal
from pydantic import BaseModel, Field
from backend.tools.base import BaseTool, resolve_column
from backend.schemas import ToolResult, ChartSpec
from backend.dataset import DatasetContext

class StatisticalAnalysisArgs(BaseModel):
    columns: Optional[List[str]] = Field(default=None, description="Columns to analyze. Default all numeric non-id.")
    statistics: Optional[List[str]] = Field(default=None, description="Stats to compute (count, missing, mean, median, mode, std, variance, min, max, range, sum, skew, kurtosis, q1, q3, iqr, percentiles)")
    percentiles: List[float] = Field(default=[5, 25, 50, 75, 95], description="Percentiles 0-100")
    group_by: Optional[str] = Field(default=None, description="Optional categorical split")

class StatisticalAnalysisTool(BaseTool):
    name = "statistical_analysis"
    description = "Compute descriptive statistics for columns (mean, median, count, spread)."
    args_schema = StatisticalAnalysisArgs
    
    def _execute(self, ctx: DatasetContext, args: StatisticalAnalysisArgs) -> ToolResult:
        warnings = []
        target_cols = []
        
        if args.columns:
            for c in args.columns:
                c_res, err = resolve_column(ctx, c)
                if err: warnings.append(err)
                else: target_cols.append(c_res)
        else:
            target_cols = [c for c, info in ctx.schema.items() if info.semantic_type == "numeric"]
            
        if not target_cols:
            return ToolResult(tool=self.name, ok=False, summary="No valid columns provided for analysis.", data={})
            
        group_col = None
        if args.group_by:
            group_col, err = resolve_column(ctx, args.group_by)
            if err: warnings.append(err)
            
        results = {}
        chart_data = {}
        suggested_charts = []
        table_rows = []
        
        df = ctx.df.copy()
        
        valid_stats = ['count', 'missing', 'mean', 'median', 'mode', 'std', 'variance', 'min', 'max', 'range', 'sum', 'skew', 'kurtosis', 'q1', 'q3', 'iqr', 'percentiles']
        req_stats = args.statistics if args.statistics else valid_stats
        req_stats = [s.lower() for s in req_stats if s.lower() in valid_stats]
        
        for col in target_cols:
            series = df[col]
            sem_type = ctx.schema[col].semantic_type
            
            if sem_type in ["numeric", "datetime"]:
                if group_col:
                    grouped = df.groupby(group_col)[col]
                    group_results = {}
                    for g_name, g_series in grouped:
                        group_results[str(g_name)] = self._compute_numeric_stats(g_series, req_stats, args.percentiles)
                    results[col] = group_results
                else:
                    results[col] = self._compute_numeric_stats(series, req_stats, args.percentiles)
                    
                chart_data[col] = series.dropna().tolist()[:1000] # max 1000 for box/hist
                
                # Dataset-aware chart suggestion (avoid box plots on small datasets)
                cat_or_id_cols = [
                    c for c, info in ctx.schema.items()
                    if info.semantic_type in ("categorical", "id_like", "text") and c != col
                ]
                best_x = group_col or (cat_or_id_cols[0] if cat_or_id_cols else None)
                if ctx.n_rows < 30 or series.nunique() < 10:
                    suggested_charts.append(ChartSpec(
                        chart_type="bar",
                        title=f"{col} by {best_x}" if best_x else f"Comparison of {col}",
                        source="dataset",
                        x=best_x,
                        y=col
                    ))
                elif group_col:
                    suggested_charts.append(ChartSpec(
                        chart_type="bar",
                        title=f"Average {col} by {group_col}",
                        source="dataset",
                        x=group_col,
                        y=col,
                        aggregation="mean"
                    ))
                else:
                    suggested_charts.append(ChartSpec(
                        chart_type="histogram",
                        title=f"Distribution of {col}",
                        source="dataset",
                        x=col,
                        bins=min(25, max(8, ctx.n_rows // 4))
                    ))
                    
            elif sem_type == "categorical" or sem_type == "boolean":
                # Fallback for non-numeric
                stats = {
                    "count": int(series.count()),
                    "missing": int(series.isna().sum()),
                    "nunique": int(series.nunique())
                }
                val_counts = series.value_counts(dropna=False).head(10).to_dict()
                stats["top_values"] = {str(k): int(v) for k, v in val_counts.items()}
                results[col] = stats
                
        # Build table
        for col, stats in results.items():
            if not group_col or ctx.schema[col].semantic_type not in ["numeric", "datetime"]:
                row = {"column": col}
                for k, v in stats.items():
                    if not isinstance(v, (dict, list)): row[k] = v
                table_rows.append(row)
            else:
                for g_name, g_stats in stats.items():
                    row = {"column": col, args.group_by: g_name}
                    for k, v in g_stats.items():
                        if not isinstance(v, (dict, list)): row[k] = v
                    table_rows.append(row)
                    
        return ToolResult(
            tool=self.name,
            ok=True,
            summary=f"Computed statistics for {len(target_cols)} columns.",
            data=results,
            table=table_rows,
            chart_data=chart_data,
            suggested_charts=suggested_charts,
            warnings=warnings
        )
        
    def _compute_numeric_stats(self, series: pd.Series, req_stats: List[str], percentiles: List[float]) -> dict:
        stats = {}
        s_clean = series.dropna()
        if len(s_clean) == 0:
            return {"missing": int(series.isna().sum())}
            
        if "count" in req_stats: stats["count"] = int(s_clean.count())
        if "missing" in req_stats: stats["missing"] = int(series.isna().sum())
        
        is_num = pd.api.types.is_numeric_dtype(series)
        
        if is_num:
            if "mean" in req_stats: stats["mean"] = float(s_clean.mean())
            if "median" in req_stats: stats["median"] = float(s_clean.median())
            if "mode" in req_stats: stats["mode"] = [float(x) for x in s_clean.mode().tolist()]
            if "std" in req_stats: stats["std"] = float(s_clean.std()) if len(s_clean) > 1 else 0.0
            if "variance" in req_stats: stats["variance"] = float(s_clean.var()) if len(s_clean) > 1 else 0.0
            if "min" in req_stats: stats["min"] = float(s_clean.min())
            if "max" in req_stats: stats["max"] = float(s_clean.max())
            if "range" in req_stats: stats["range"] = float(s_clean.max() - s_clean.min())
            if "sum" in req_stats: stats["sum"] = float(s_clean.sum())
            if "skew" in req_stats: stats["skew"] = float(s_clean.skew()) if len(s_clean) > 2 else 0.0
            if "kurtosis" in req_stats: stats["kurtosis"] = float(s_clean.kurtosis()) if len(s_clean) > 3 else 0.0
            if "q1" in req_stats: stats["q1"] = float(s_clean.quantile(0.25))
            if "q3" in req_stats: stats["q3"] = float(s_clean.quantile(0.75))
            if "iqr" in req_stats: stats["iqr"] = float(s_clean.quantile(0.75) - s_clean.quantile(0.25))
            if "percentiles" in req_stats:
                stats["percentiles"] = {f"p{p}": float(s_clean.quantile(p/100)) for p in percentiles}
                
        else: # datetime
            if "min" in req_stats: stats["min"] = s_clean.min().isoformat()
            if "max" in req_stats: stats["max"] = s_clean.max().isoformat()
            
        return self._clean_dict(stats)
        
    def _clean_dict(self, d: dict) -> dict:
        res = {}
        for k, v in d.items():
            if isinstance(v, list): res[k] = v
            elif pd.isna(v): res[k] = None
            elif isinstance(v, float) and (np.isnan(v) or np.isinf(v)): res[k] = None
            elif isinstance(v, dict): res[k] = self._clean_dict(v)
            else: res[k] = v
        return res
