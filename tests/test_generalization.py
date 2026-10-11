import pytest
import pandas as pd
from backend.dataset import clean_and_profile_dataset
from backend.tools import TOOL_REGISTRY
from backend.tools.statistical_analysis import StatisticalAnalysisTool
from backend.tools.aggregate_data import AggregateDataTool
from backend.tools.correlation_analysis import CorrelationAnalysisTool
from backend.tools.outlier_detection import OutlierDetectionTool
from backend.tools.time_series_analysis import TimeSeriesAnalysisTool
from backend.report.builder import build_report_evidence, build_template_fallback_report
from backend.report.pdf import build_pdf_report

@pytest.fixture
def fixtures():
    # 1. Retail Sales (Dates, categories, numeric)
    df_sales = pd.DataFrame({
        "order_id": [f"ORD_{i}" for i in range(1, 11)],
        "revenue": [150.0, 200.5, 45.0, 99.9, 1200.0, 310.0, 520.0, 80.0, 210.0, 15.0],
        "quantity": [2, 3, 1, 1, 10, 4, 5, 1, 2, 1],
        "category": ["Electronics", "Books", "Clothing", "Clothing", "Electronics", "Books", "Electronics", "Clothing", "Books", "Books"],
        "date": ["2023-01-01", "2023-01-02", "2023-01-05", "2023-01-10", "2023-01-15", "2023-01-20", "2023-01-25", "2023-02-01", "2023-02-05", "2023-02-10"]
    })

    # 2. HR Dataset (No dates, employee records)
    df_hr = pd.DataFrame({
        "emp_id": [f"EMP{i}" for i in range(101, 111)],
        "department": ["Engineering", "HR", "Marketing", "Engineering", "Engineering", "Marketing", "HR", "Finance", "Finance", "Engineering"],
        "salary": [95000, 62000, 71000, 120000, 105000, 68000, 59000, 88000, 92000, 135000],
        "performance_score": [4, 3, 3, 5, 4, 3, 2, 4, 4, 5],
        "remote": ["Yes", "No", "Yes", "Yes", "No", "Yes", "No", "No", "Yes", "Yes"]
    })

    # 3. IoT Sensor stream (Numeric telemetry, no categories, no dates)
    df_iot = pd.DataFrame({
        "sensor_a": [21.5, 21.8, 22.1, 21.9, 22.4, 23.0, 22.8, 21.6, 22.0, 22.2],
        "sensor_b": [55.2, 54.8, 56.1, 55.9, 57.0, 61.2, 58.0, 55.0, 56.2, 55.8],
        "voltage": [3.3, 3.29, 3.31, 3.3, 3.28, 3.29, 3.32, 3.3, 3.31, 3.29]
    })

    return {
        "sales": clean_and_profile_dataset("retail_sales.csv", df_sales),
        "hr": clean_and_profile_dataset("hr_roster.xlsx", df_hr),
        "iot": clean_and_profile_dataset("iot_sensors.csv", df_iot)
    }

def test_generalization_across_datasets(fixtures):
    for name, ctx in fixtures.items():
        # Every dataset must profile cleanly
        assert ctx.n_rows == 10
        assert ctx.n_cols >= 3
        
        # 1. Statistical analysis should work on all
        stats_tool = TOOL_REGISTRY["statistical_analysis"]
        res_stats = stats_tool.run(ctx)
        assert res_stats.ok, f"Failed stats on {name}"
        
        # 2. Outlier detection should work on all numeric datasets
        out_tool = TOOL_REGISTRY["outlier_detection"]
        res_out = out_tool.run(ctx)
        assert res_out.ok, f"Failed outliers on {name}"
        
        # 3. Correlation should work on all (since each has >= 2 numeric columns)
        corr_tool = TOOL_REGISTRY["correlation_analysis"]
        res_corr = corr_tool.run(ctx)
        assert res_corr.ok, f"Failed corr on {name}"

        # 4. Time series should handle gracefully
        ts_tool = TOOL_REGISTRY["time_series_analysis"]
        res_ts = ts_tool.run(ctx, value_columns=[list(ctx.schema.keys())[1]])
        if name == "sales":
            assert res_ts.ok, "Sales has dates, should succeed"
        else:
            # HR and IoT don't have dates -> must return ok=False with clean message
            assert not res_ts.ok, f"{name} has no dates, should return ok=False"
            assert "date" in (res_ts.error or "").lower() or "date" in res_ts.summary.lower()

        # 5. PDF Report must build cleanly for all fixtures
        evidence, tool_results, not_performed = build_report_evidence(ctx)
        draft = build_template_fallback_report(ctx, evidence, not_performed, tool_results)
        pdf_bytes = build_pdf_report(draft, ctx, tool_results)
        assert len(pdf_bytes) > 1000
        assert pdf_bytes.startswith(b"%PDF")
