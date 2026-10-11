from backend.tools.base import BaseTool
from backend.tools.filter_data import FilterDataTool
from backend.tools.statistical_analysis import StatisticalAnalysisTool
from backend.tools.aggregate_data import AggregateDataTool
from backend.tools.correlation_analysis import CorrelationAnalysisTool
from backend.tools.outlier_detection import OutlierDetectionTool
from backend.tools.time_series_analysis import TimeSeriesAnalysisTool

TOOL_REGISTRY = {
    FilterDataTool.name: FilterDataTool(),
    StatisticalAnalysisTool.name: StatisticalAnalysisTool(),
    AggregateDataTool.name: AggregateDataTool(),
    CorrelationAnalysisTool.name: CorrelationAnalysisTool(),
    OutlierDetectionTool.name: OutlierDetectionTool(),
    TimeSeriesAnalysisTool.name: TimeSeriesAnalysisTool()
}

def get_tool(name: str) -> BaseTool:
    return TOOL_REGISTRY.get(name)
    
def get_tool_schemas():
    schemas = []
    for tool in TOOL_REGISTRY.values():
        schemas.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.args_schema.model_json_schema()
            }
        })
    return schemas
