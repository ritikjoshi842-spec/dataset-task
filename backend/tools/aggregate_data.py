import pandas as pd
from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field
from backend.tools.base import BaseTool, resolve_column
from backend.schemas import ToolResult, Condition, ChartSpec
from backend.dataset import DatasetContext

class AggregationDef(BaseModel):
    column: Optional[str] = Field(default=None, description="Column to aggregate (or use 'field')")
    field: Optional[str] = Field(default=None, description="Alias for column")
    function: Optional[str] = Field(default="count", description="Function: sum, mean, median, count, nunique, min, max, std (or use 'operation')")
    operation: Optional[str] = Field(default=None, description="Alias for function")
    alias: Optional[str] = Field(default=None, description="Optional alias for resulting column")

class AggregateDataArgs(BaseModel):
    group_by: List[str] = Field(description="Columns to group by (1-3)")
    aggregations: List[AggregationDef] = Field(description="Aggregations to perform")
    filters: Optional[List[Condition]] = Field(default=None, description="Filters to apply first")
    sort_by: Optional[str] = Field(default=None, description="Column to sort by")
    ascending: bool = Field(default=False, description="Sort ascending")
    top_n: Optional[int] = Field(default=None, description="Return top N rows")
    include_total: bool = Field(default=False, description="Include share-of-total column for sum")

class AggregateDataTool(BaseTool):
    name = "aggregate_data"
    description = "Group data by categories and compute aggregated metrics."
    args_schema = AggregateDataArgs
    
    def _execute(self, ctx: DatasetContext, args: AggregateDataArgs) -> ToolResult:
        df = ctx.df.copy()
        warnings = []
        
        group_cols = []
        for g in args.group_by[:3]:
            res, err = resolve_column(ctx, g)
            if err: return ToolResult(tool=self.name, ok=False, summary=err, data={})
            group_cols.append(res)
            
        agg_dict = {}
        alias_map = {}
        for a in args.aggregations:
            raw_col = a.column or a.field
            raw_func = (a.function or a.operation or "count").lower()
            
            if not raw_col:
                raw_col = df.columns[0]
                
            res, err = resolve_column(ctx, raw_col)
            if err: return ToolResult(tool=self.name, ok=False, summary=err, data={})
            
            # Map common function synonyms
            if raw_func in ["total", "sum"]: raw_func = "sum"
            elif raw_func in ["avg", "average", "mean"]: raw_func = "mean"
            elif raw_func in ["cnt", "count"]: raw_func = "count"
            elif raw_func in ["distinct", "unique", "nunique"]: raw_func = "nunique"
            
            # check type for numeric functions
            if raw_func in ['sum', 'mean', 'median', 'std']:
                if ctx.schema[res].semantic_type not in ['numeric', 'boolean']:
                    return ToolResult(tool=self.name, ok=False, summary=f"Cannot compute {raw_func} on non-numeric column {res}", data={})
            
            if res not in agg_dict:
                agg_dict[res] = []
            agg_dict[res].append(raw_func)
            
            if a.alias:
                alias_map[f"{res}_{raw_func}"] = a.alias
            
        grouped = df.groupby(group_cols, dropna=False).agg(agg_dict)
        
        # flatten multi-index columns
        if isinstance(grouped.columns, pd.MultiIndex):
            grouped.columns = [f"{col}_{func}" if func != "size" else "count" for col, func in grouped.columns]
            
        grouped = grouped.reset_index()
        
        # Apply aliases if provided
        if alias_map:
            grouped = grouped.rename(columns=alias_map)
        
        # Share of total
        if args.include_total:
            for c in grouped.columns:
                if c.endswith('_sum'):
                    total = grouped[c].sum()
                    if total != 0:
                        grouped[f"{c}_pct"] = (grouped[c] / total) * 100
                        
        if args.sort_by:
            sort_col = args.sort_by
            if sort_col not in grouped.columns:
                for c in grouped.columns:
                    if sort_col in c:
                        sort_col = c
                        break
            if sort_col in grouped.columns:
                grouped = grouped.sort_values(by=sort_col, ascending=args.ascending)
                
        if args.top_n:
            grouped = grouped.head(args.top_n)
            
        table = grouped.to_dict(orient='records')
        
        # clean for json
        for row in table:
            for k, v in row.items():
                if pd.isna(v): row[k] = None
                elif isinstance(v, (pd.Timestamp, float)) and pd.isna(v): row[k] = None
        
        y_col = grouped.columns[-1] if len(grouped.columns) > len(group_cols) else None
        
        suggested_charts = []
        if len(group_cols) > 0 and y_col:
            suggested_charts.append(ChartSpec(
                chart_type="bar",
                title=f"{y_col} by {group_cols[0]}",
                source="tool_result",
                x=group_cols[0],
                y=y_col,
                color=group_cols[1] if len(group_cols) > 1 else None,
                stacked=True if len(group_cols) > 1 else False,
                orientation="h" if grouped[group_cols[0]].astype(str).str.len().max() > 10 else "v"
            ))
            
        return ToolResult(
            tool=self.name,
            ok=True,
            summary=f"Aggregated {len(args.aggregations)} metrics by {', '.join(group_cols)}.",
            data={"rows": len(grouped)},
            table=table,
            chart_data=grouped.to_dict(orient='list'),
            suggested_charts=suggested_charts,
            warnings=warnings
        )
