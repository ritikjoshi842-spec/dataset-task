import pandas as pd
from typing import List, Optional, Literal
from pydantic import BaseModel, Field
from backend.tools.base import BaseTool, resolve_column
from backend.schemas import ToolResult, Condition
from backend.dataset import DatasetContext

class FilterDataArgs(BaseModel):
    conditions: Optional[List[Condition]] = Field(default_factory=list, description="List of conditions to filter by")
    logic: Literal["and", "or"] = Field(default="and", description="Logic to combine conditions")
    columns: Optional[List[str]] = Field(default=None, description="Columns to return (projection)")
    fields: Optional[List[str]] = Field(default=None, description="Alternative for columns")
    sort_by: Optional[str] = Field(default=None, description="Column to sort by")
    ascending: bool = Field(default=True, description="Sort ascending")
    limit: int = Field(default=100, description="Max rows to return", le=1000)

class FilterDataTool(BaseTool):
    name = "filter_data"
    description = "Filter and sort the dataset based on specific conditions."
    args_schema = FilterDataArgs
    
    def _execute(self, ctx: DatasetContext, args: FilterDataArgs) -> ToolResult:
        df = ctx.df.copy()
        mask = None
        applied_conditions = []
        warnings = []
        
        if args.conditions:
            for cond in args.conditions:
                raw_col = cond.column or cond.field
                if not raw_col:
                    continue
                col, err = resolve_column(ctx, raw_col)
                if err:
                    return ToolResult(tool=self.name, ok=False, summary="Column not found", data={}, error=err)
                    
                series = df[col]
                sem_type = ctx.schema[col].semantic_type
                op = cond.operator or cond.op or "=="
                val = cond.value
                
                # Type coercion
                if sem_type == "numeric" and val is not None:
                    try:
                        val = float(val)
                    except ValueError:
                        pass
                elif sem_type == "datetime" and val is not None:
                    try:
                        val = pd.to_datetime(val)
                    except Exception:
                        pass
                        
                # Create mask
                try:
                    if op == "==":
                        if sem_type == "text" and isinstance(val, str):
                            m = series.astype(str).str.lower() == str(val).lower()
                        else:
                            m = series == val
                    elif op == "!=":
                        if sem_type == "text" and isinstance(val, str):
                            m = series.astype(str).str.lower() != str(val).lower()
                        else:
                            m = series != val
                    elif op == ">": m = series > val
                    elif op == ">=": m = series >= val
                    elif op == "<": m = series < val
                    elif op == "<=": m = series <= val
                    elif op == "between": m = series.between(val, cond.value2)
                    elif op == "in": m = series.isin(val if isinstance(val, list) else [val])
                    elif op == "not_in": m = ~series.isin(val if isinstance(val, list) else [val])
                    elif op == "contains": m = series.astype(str).str.contains(str(val), case=False, na=False)
                    elif op == "not_contains": m = ~series.astype(str).str.contains(str(val), case=False, na=False)
                    elif op == "startswith": m = series.astype(str).str.startswith(str(val), na=False)
                    elif op == "endswith": m = series.astype(str).str.endswith(str(val), na=False)
                    elif op == "is_null": m = series.isna()
                    elif op == "not_null": m = series.notna()
                    else:
                        m = pd.Series([True] * len(df), index=df.index)
                        
                    applied_conditions.append(f"{col} {op} {val}")
                        
                    if mask is None:
                        mask = m
                    else:
                        if args.logic == "and": mask = mask & m
                        else: mask = mask | m
                except Exception as e:
                    warnings.append(f"Failed to apply condition {col} {op} {val}: {str(e)}")
                    
        if mask is not None:
            df = df[mask]
            
        total_matches = len(df)
        pct_matched = round((total_matches / ctx.n_rows) * 100, 2) if ctx.n_rows > 0 else 0
        
        if args.sort_by:
            scol, err = resolve_column(ctx, args.sort_by)
            if err:
                warnings.append(err)
            else:
                df = df.sort_values(by=scol, ascending=args.ascending)
                
        if args.columns:
            valid_cols = []
            for c in args.columns:
                c_resolved, err = resolve_column(ctx, c)
                if c_resolved:
                    valid_cols.append(c_resolved)
            if valid_cols:
                df = df[valid_cols]
                
        row_count_returned = min(total_matches, args.limit)
        df_return = df.head(row_count_returned)
        
        table_data = []
        for row in df_return.to_dict(orient='records'):
            # clean nan/inf for json
            cleaned = {}
            for k, v in row.items():
                if pd.isna(v): cleaned[k] = None
                elif isinstance(v, pd.Timestamp): cleaned[k] = v.isoformat()
                else: cleaned[k] = v
            table_data.append(cleaned)
            
        summary = f"Filtered data: {total_matches} rows matched ({pct_matched}%)."
        if total_matches == 0:
            summary = "0 rows matched the applied conditions."
            
        return ToolResult(
            tool=self.name,
            ok=True,
            summary=summary,
            data={
                "total_matches": total_matches,
                "row_count_returned": row_count_returned,
                "pct_matched": pct_matched,
                "applied_conditions": applied_conditions
            },
            table=table_data,
            warnings=warnings
        )
