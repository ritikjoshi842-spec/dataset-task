from pydantic import BaseModel
from typing import Type, Any
from backend.dataset import DatasetContext
from backend.schemas import ToolResult
import difflib
import traceback

class BaseTool:
    name: str = ""
    description: str = ""
    args_schema: Type[BaseModel]
    
    def run(self, ctx: DatasetContext, **kwargs) -> ToolResult:
        try:
            args = self.args_schema(**kwargs)
            return self._execute(ctx, args)
        except Exception as e:
            # Catch all exceptions and return a safe error message
            # traceback.print_exc() could be logged here
            return ToolResult(
                tool=self.name,
                ok=False,
                summary=f"Failed to execute {self.name}",
                data={},
                error=f"Error during {self.name}: {str(e)}"
            )
            
    def _execute(self, ctx: DatasetContext, args: BaseModel) -> ToolResult:
        raise NotImplementedError
        
def resolve_column(ctx: DatasetContext, name: str, allowed_types: list[str] = None) -> tuple[str | None, str | None]:
    if not name:
        return None, "Column name is empty."
        
    cols = list(ctx.schema.keys())
    
    if name in cols:
        resolved = name
    else:
        lower_cols = {c.lower(): c for c in cols}
        if name.lower() in lower_cols:
            resolved = lower_cols[name.lower()]
        else:
            matches = difflib.get_close_matches(name, cols, n=3, cutoff=0.6)
            if matches:
                return None, f"Column '{name}' not found. Did you mean {', '.join([repr(m) for m in matches])}?"
            return None, f"Column '{name}' not found in the dataset."
            
    if allowed_types:
        col_type = ctx.schema[resolved].semantic_type
        if col_type not in allowed_types:
            return None, f"Column '{resolved}' is of type '{col_type}', but must be one of {allowed_types}."
            
    return resolved, None
