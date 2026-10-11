import pandas as pd
import numpy as np
from typing import List, Optional, Literal
from pydantic import BaseModel, Field
from backend.tools.base import BaseTool, resolve_column
from backend.schemas import ToolResult, ChartSpec
from backend.dataset import DatasetContext

class OutlierDetectionArgs(BaseModel):
    columns: Optional[List[str]] = Field(default=None, description="Numeric columns to check")
    method: Literal["iqr", "zscore"] = Field(default="iqr")
    iqr_multiplier: float = Field(default=1.5)
    z_threshold: float = Field(default=3.0)
    max_rows_returned: int = Field(default=100)

class OutlierDetectionTool(BaseTool):
    name = "outlier_detection"
    description = "Detect potential outliers in numeric columns."
    args_schema = OutlierDetectionArgs
    
    def _execute(self, ctx: DatasetContext, args: OutlierDetectionArgs) -> ToolResult:
        warnings = ["Values identified are potential outliers — not necessarily errors."]
        
        cols = []
        if args.columns:
            for c in args.columns:
                res, err = resolve_column(ctx, c, allowed_types=["numeric"])
                if err: warnings.append(err)
                else: cols.append(res)
        else:
            cols = [c for c, info in ctx.schema.items() if info.semantic_type == "numeric"]
            
        if not cols:
            return ToolResult(tool=self.name, ok=False, summary="No numeric columns for outlier detection.", data={})
            
        results = {}
        outlier_rows = pd.DataFrame()
        suggested_charts = []
        chart_data = {}
        
        for col in cols:
            series = ctx.df[col]
            s_clean = series.dropna()
            
            if len(s_clean) < 8:
                warnings.append(f"Skipping {col}: too few valid values (<8).")
                continue
                
            if s_clean.nunique() <= 1:
                warnings.append(f"Skipping {col}: constant column.")
                continue
                
            lower, upper = None, None
            if args.method == "iqr":
                q1 = s_clean.quantile(0.25)
                q3 = s_clean.quantile(0.75)
                iqr = q3 - q1
                if iqr == 0:
                    warnings.append(f"Skipping {col}: IQR is 0.")
                    continue
                lower = q1 - (args.iqr_multiplier * iqr)
                upper = q3 + (args.iqr_multiplier * iqr)
            elif args.method == "zscore":
                mean = s_clean.mean()
                std = s_clean.std(ddof=1)
                if std == 0:
                    warnings.append(f"Skipping {col}: Standard deviation is 0.")
                    continue
                lower = mean - (args.z_threshold * std)
                upper = mean + (args.z_threshold * std)
                
            outliers = series[(series < lower) | (series > upper)]
            n_outliers = len(outliers)
            
            low_count = len(series[series < lower])
            high_count = len(series[series > upper])
            
            results[col] = {
                "lower_threshold": float(lower),
                "upper_threshold": float(upper),
                "outlier_count": int(n_outliers),
                "outlier_pct": float(round((n_outliers / len(s_clean)) * 100, 2)),
                "low_outliers": int(low_count),
                "high_outliers": int(high_count)
            }
            
            if n_outliers > 0:
                mask = (ctx.df[col] < lower) | (ctx.df[col] > upper)
                col_outliers_df = ctx.df[mask].copy()
                col_outliers_df['_outlier_reason'] = f"{col} out of bounds"
                outlier_rows = pd.concat([outlier_rows, col_outliers_df])
                
            if n_outliers > 0:
                if ctx.n_rows >= 30:
                    suggested_charts.append(ChartSpec(
                        chart_type="box",
                        title=f"Outliers in {col}",
                        source="dataset",
                        y=col
                    ))
                else:
                    cat_cols = [c for c, info in ctx.schema.items() if info.semantic_type in ("categorical", "id_like", "text")]
                    x_col = cat_cols[0] if cat_cols else None
                    suggested_charts.append(ChartSpec(
                        chart_type="bar",
                        title=f"{col} Values (with Standout Records)",
                        source="dataset",
                        x=x_col,
                        y=col
                    ))
            
            # just send a sample for chart data
            chart_data[col] = s_clean.tolist()[:1000]
            
        if len(outlier_rows) > 0:
            outlier_rows = outlier_rows.drop_duplicates().head(args.max_rows_returned)
            table = outlier_rows.to_dict(orient="records")
            # clean nan
            for row in table:
                for k, v in row.items():
                    if pd.isna(v): row[k] = None
                    elif isinstance(v, (pd.Timestamp, float)) and pd.isna(v): row[k] = None
        else:
            table = []
            
        return ToolResult(
            tool=self.name,
            ok=True,
            summary=f"Detected outliers in {len(results)} columns using {args.method.upper()}.",
            data=results,
            table=table,
            chart_data=chart_data,
            suggested_charts=suggested_charts[:4],
            warnings=warnings
        )
