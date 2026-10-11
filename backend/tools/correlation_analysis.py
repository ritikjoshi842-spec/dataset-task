import pandas as pd
import numpy as np
from typing import List, Optional, Literal
from pydantic import BaseModel, Field
from backend.tools.base import BaseTool, resolve_column
from backend.schemas import ToolResult, ChartSpec
from backend.dataset import DatasetContext
import itertools

class CorrelationAnalysisArgs(BaseModel):
    columns: Optional[List[str]] = Field(default=None, description="Numeric columns to analyze")
    method: Literal["pearson", "spearman"] = Field(default="pearson")
    target: Optional[str] = Field(default=None, description="Target column to correlate against")
    min_periods: int = Field(default=5)

class CorrelationAnalysisTool(BaseTool):
    name = "correlation_analysis"
    description = "Calculate correlation coefficients between numeric columns to find relationships."
    args_schema = CorrelationAnalysisArgs
    
    def _get_strength_label(self, r: float) -> str:
        if pd.isna(r): return "unknown"
        abs_r = abs(r)
        if abs_r < 0.2: return "negligible"
        if abs_r < 0.4: return "weak"
        if abs_r < 0.6: return "moderate"
        if abs_r < 0.8: return "strong"
        return "very strong"

    def _execute(self, ctx: DatasetContext, args: CorrelationAnalysisArgs) -> ToolResult:
        warnings = ["Correlation indicates association, not causation."]
        
        cols = []
        if args.columns:
            for c in args.columns:
                res, err = resolve_column(ctx, c, allowed_types=["numeric"])
                if err: warnings.append(err)
                else: cols.append(res)
        else:
            cols = [c for c, info in ctx.schema.items() if info.semantic_type == "numeric"]
            
        if args.target:
            t_res, err = resolve_column(ctx, args.target, allowed_types=["numeric"])
            if err: return ToolResult(tool=self.name, ok=False, summary=err, data={})
            if t_res not in cols: cols.append(t_res)
            
        if len(cols) < 2:
            return ToolResult(tool=self.name, ok=False, summary="Requires at least 2 numeric columns.", data={})
            
        df = ctx.df[cols].copy()
        
        # Drop constant columns
        for c in cols:
            if df[c].nunique() <= 1:
                df.drop(columns=[c], inplace=True)
                warnings.append(f"Column '{c}' was dropped because it is constant.")
                
        if len(df.columns) < 2:
            return ToolResult(tool=self.name, ok=False, summary="Not enough varying numeric columns for correlation.", data={})
            
        corr_matrix = df.corr(method=args.method, min_periods=args.min_periods)
        
        results = {}
        chart_data = {"matrix": corr_matrix.replace({np.nan: None}).to_dict()}
        suggested_charts = []
        table = []
        
        if args.target and args.target in df.columns:
            target = args.target
            corrs = corr_matrix[target].drop(target).dropna().sort_values(key=abs, ascending=False)
            
            for c, r in corrs.items():
                label = self._get_strength_label(r)
                table.append({
                    "feature": c,
                    "target": target,
                    "correlation": round(r, 4),
                    "strength": label
                })
                
            results["target_correlations"] = table
            summary = f"Correlations with {target} computed."
            
            if len(corrs) > 0:
                top_feature = corrs.index[0]
                suggested_charts.append(ChartSpec(
                    chart_type="scatter",
                    title=f"{target} vs {top_feature}",
                    source="dataset",
                    x=top_feature,
                    y=target
                ))
        else:
            pairs = []
            for i, j in itertools.combinations(corr_matrix.columns, 2):
                r = corr_matrix.loc[i, j]
                if pd.notna(r):
                    pairs.append({
                        "feature1": i,
                        "feature2": j,
                        "correlation": round(r, 4),
                        "strength": self._get_strength_label(r),
                        "abs_r": abs(r)
                    })
                    
            pairs.sort(key=lambda x: x["abs_r"], reverse=True)
            top_k = pairs[:10]
            
            for p in top_k:
                table.append({
                    "feature1": p["feature1"],
                    "feature2": p["feature2"],
                    "correlation": p["correlation"],
                    "strength": p["strength"]
                })
                
            results["top_pairs"] = table
            summary = f"Computed {args.method} correlation matrix for {len(df.columns)} columns."
            
            if len(pairs) > 0:
                p = pairs[0]
                suggested_charts.append(ChartSpec(
                    chart_type="scatter",
                    title=f"{p['feature1']} vs {p['feature2']}",
                    source="dataset",
                    x=p['feature1'],
                    y=p['feature2']
                ))

            if len(df.columns) >= 3:
                suggested_charts.append(ChartSpec(
                    chart_type="heatmap",
                    title=f"{args.method.capitalize()} Correlation Matrix",
                    source="tool_result",
                    x=None, y=None
                ))

        return ToolResult(
            tool=self.name,
            ok=True,
            summary=summary,
            data=results,
            table=table,
            chart_data=chart_data,
            suggested_charts=suggested_charts,
            warnings=warnings
        )
