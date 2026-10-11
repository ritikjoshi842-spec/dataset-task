import pandas as pd
import numpy as np
from typing import List, Optional, Literal
from pydantic import BaseModel, Field
from backend.tools.base import BaseTool, resolve_column
from backend.schemas import ToolResult, Condition, ChartSpec
from backend.dataset import DatasetContext

class TimeSeriesAnalysisArgs(BaseModel):
    date_column: Optional[str] = Field(default=None, description="Datetime column")
    value_columns: List[str] = Field(description="Numeric columns to aggregate over time")
    aggregation: Literal["sum", "mean", "count", "min", "max", "median"] = Field(default="sum")
    frequency: Optional[Literal["D", "W", "M", "Q", "Y"]] = Field(default=None, description="Time frequency")
    filters: Optional[List[Condition]] = Field(default=None)
    group_by: Optional[str] = Field(default=None, description="Optional single categorical split")

class TimeSeriesAnalysisTool(BaseTool):
    name = "time_series_analysis"
    description = "Analyze trends over time."
    args_schema = TimeSeriesAnalysisArgs
    
    def _execute(self, ctx: DatasetContext, args: TimeSeriesAnalysisArgs) -> ToolResult:
        warnings = []
        df = ctx.df.copy()
        
        date_col = None
        if args.date_column:
            res, err = resolve_column(ctx, args.date_column, ["datetime"])
            if err: return ToolResult(tool=self.name, ok=False, summary=err, data={})
            date_col = res
        else:
            # auto-pick
            for c, info in ctx.schema.items():
                if info.semantic_type == "datetime":
                    date_col = c
                    break
            if not date_col:
                return ToolResult(tool=self.name, ok=False, summary="No date column found. Time-based analysis cannot be performed.", data={}, error="No date column found.")
                
        val_cols = []
        for v in args.value_columns:
            res, err = resolve_column(ctx, v, ["numeric", "boolean"])
            if err: warnings.append(err)
            else: val_cols.append(res)
            
        if not val_cols:
            if args.aggregation == "count":
                val_cols = [df.columns[0]] # Just count rows
            else:
                return ToolResult(tool=self.name, ok=False, summary="No valid numeric columns for aggregation.", data={})
                
        group_col = None
        if args.group_by:
            res, err = resolve_column(ctx, args.group_by)
            if err: warnings.append(err)
            else: group_col = res
            
        df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
        nat_count = df[date_col].isna().sum()
        if nat_count > 0:
            warnings.append(f"Dropped {nat_count} rows with invalid dates.")
            df = df.dropna(subset=[date_col])
            
        if len(df) == 0:
            return ToolResult(tool=self.name, ok=False, summary="No valid data after date parsing.", data={})
            
        df = df.sort_values(date_col)
        
        freq = args.frequency
        if not freq:
            span = df[date_col].max() - df[date_col].min()
            if span.days <= 90: freq = "D"
            elif span.days <= 730: freq = "M"
            else: freq = "Y"
            
        # Group by
        if group_col:
            # limit to top 8 groups
            top_groups = df[group_col].value_counts().nlargest(8).index
            df[group_col] = df[group_col].apply(lambda x: x if x in top_groups else "Other")
            
            pivot = df.pivot_table(index=date_col, columns=group_col, values=val_cols[0], aggfunc=args.aggregation)
            resampled = pivot.resample(freq).sum() if args.aggregation == 'sum' else pivot.resample(freq).mean()
        else:
            grouped = df.set_index(date_col)[val_cols].resample(freq)
            resampled = getattr(grouped, args.aggregation)()
            
        resampled = resampled.fillna(0) if args.aggregation in ['count', 'sum'] else resampled
        
        results = {}
        
        # Calculate trends
        for col in resampled.columns:
            series = resampled[col].dropna()
            if len(series) < 2: continue
            
            changes = series.pct_change()
            
            col_str = str(col)
            results[col_str] = {
                "start_val": float(series.iloc[0]),
                "end_val": float(series.iloc[-1]),
                "best_period": str(series.idxmax().date()),
                "worst_period": str(series.idxmin().date()),
            }
            
            x = np.arange(len(series))
            y = series.values
            if len(x) > 1:
                slope, _ = np.polyfit(x, y, 1)
                results[col_str]["trend_slope"] = float(slope)
                results[col_str]["trend_direction"] = "increasing" if slope > 0 else "decreasing"
                
        # table
        res_reset = resampled.reset_index()
        res_reset[date_col] = res_reset[date_col].dt.strftime('%Y-%m-%d')
        table = res_reset.to_dict(orient="records")
        for row in table:
            for k, v in row.items():
                if pd.isna(v): row[k] = None
                elif isinstance(v, float) and (np.isnan(v) or np.isinf(v)): row[k] = None
                
        # chart data
        chart_data = res_reset.to_dict(orient="list")
        
        suggested_charts = [ChartSpec(
            chart_type="line",
            title=f"{args.aggregation.capitalize()} of {val_cols[0]} over time",
            source="tool_result",
            x=date_col,
            y=val_cols[0] if not group_col else [str(c) for c in resampled.columns],
        )]
            
        return ToolResult(
            tool=self.name,
            ok=True,
            summary=f"Time series analysis grouped by {freq}.",
            data=results,
            table=table,
            chart_data=chart_data,
            suggested_charts=suggested_charts,
            warnings=warnings
        )
