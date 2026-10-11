from pydantic import BaseModel, Field
from typing import Literal, Optional, Any, Dict, List

class Condition(BaseModel):
    column: Optional[str] = Field(default=None, description="Column name (or use 'field')")
    field: Optional[str] = Field(default=None, description="Alternative name for column")
    operator: Optional[str] = Field(default="==", description="Comparison operator: ==, !=, >, >=, <, <=, between, in, not_in, contains, etc.")
    op: Optional[str] = Field(default=None, description="Alternative name for operator")
    value: Any = None
    value2: Optional[Any] = None

class ChartSpec(BaseModel):
    chart_type: Literal["bar", "line", "histogram", "scatter", "box", "heatmap"]
    title: str
    source: Literal["tool_result", "dataset"]
    tool_result_id: Optional[str] = None
    x: Optional[str] = None
    y: Optional[str | List[str]] = None
    color: Optional[str] = None
    aggregation: Optional[Literal["sum", "mean", "median", "count", "min", "max"]] = None
    filters: Optional[List[Condition]] = None
    orientation: Literal["v", "h"] = "v"
    bins: Optional[int] = None
    top_n: Optional[int] = None
    sort: Literal["asc", "desc", "none"] = "none"
    stacked: bool = False
    x_label: Optional[str] = None
    y_label: Optional[str] = None

class ToolResult(BaseModel):
    tool: str
    ok: bool
    summary: str
    data: Dict[str, Any]
    table: Optional[List[Dict[str, Any]]] = None
    chart_data: Optional[Dict[str, Any]] = None
    suggested_charts: List[ChartSpec] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    error: Optional[str] = None

class Block(BaseModel):
    type: Literal["markdown", "chart", "table"]
    text: Optional[str] = None
    chart: Optional[ChartSpec] = None
    table_ref: Optional[str] = None
    caption: Optional[str] = None

class ToolCallRecord(BaseModel):
    name: str
    args: Dict[str, Any]
    ok: bool
    summary: str
    duration_ms: int

class AgentResponse(BaseModel):
    blocks: List[Block]
    tool_trace: List[ToolCallRecord]
    warnings: List[str]

class Finding(BaseModel):
    statement: str
    evidence: Optional[str] = ""
    confidence_note: Optional[str] = None

class ReportSection(BaseModel):
    heading: str
    body_markdown: str = ""
    findings: List[Finding] = Field(default_factory=list)
    chart_specs: List[ChartSpec] = Field(default_factory=list)

class ReportDraft(BaseModel):
    title: str
    plain_english_guide: Optional[str] = ""
    executive_summary: str
    sections: List[ReportSection] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    not_performed: List[str] = Field(default_factory=list)
