import pytest
import pandas as pd
from backend.dataset import clean_and_profile_dataset
from backend.report.builder import build_report_evidence, build_template_fallback_report
from backend.report.pdf import build_pdf_report

@pytest.fixture
def sample_dataset():
    df = pd.DataFrame({
        "sales": [100, 200, 300, 400, 500, 10000],
        "profit": [20, 40, 50, 70, 110, 2000],
        "date": ["2023-01-01", "2023-01-02", "2023-01-03", "2023-01-04", "2023-01-05", "2023-01-06"],
        "category": ["A", "B", "A", "B", "C", "C"]
    })
    return clean_and_profile_dataset("test_sales", df)

def test_report_pipeline(sample_dataset):
    evidence, tool_results, not_performed = build_report_evidence(sample_dataset)
    assert "statistical_analysis" in evidence["tool_results"]
    assert "report_stats" in tool_results
    assert tool_results["report_stats"].ok
    
    draft = build_template_fallback_report(sample_dataset, evidence, not_performed, tool_results)
    assert len(draft.sections) > 0
    assert draft.plain_english_guide and len(draft.plain_english_guide) > 50
    
    pdf_bytes = build_pdf_report(draft, sample_dataset, tool_results)
    assert len(pdf_bytes) > 1000
    assert pdf_bytes.startswith(b"%PDF")

def test_user_requested_chart_gating():
    from backend.agent import user_requested_chart
    # Normal summary / analytical queries should NOT trigger charts
    assert user_requested_chart("summarise the dataset for me") is False
    assert user_requested_chart("what is the average cost for two by country?") is False
    assert user_requested_chart("give me a breakdown of the top 5 cuisines") is False
    assert user_requested_chart("explain what this dataset is about") is False
    
    # Explicit chart/graph queries SHOULD trigger charts
    assert user_requested_chart("show me a bar chart of top cuisines") is True
    assert user_requested_chart("plot a graph of ratings vs votes") is True
    assert user_requested_chart("visualize the distribution of sales as a histogram") is True


def test_small_dataset_report_avoids_box_plots(sample_dataset):
    from backend.viz.spec import curate_report_charts
    evidence, tool_results, not_performed = build_report_evidence(sample_dataset)
    curated = curate_report_charts(sample_dataset, tool_results)
    assert len(curated) > 0
    assert all(c.chart_type != "box" for c in curated), "Small datasets (<30 rows) should never default to box plots in reports"

    draft = build_template_fallback_report(sample_dataset, evidence, not_performed, tool_results)
    for sec in draft.sections:
        for ch in sec.chart_specs:
            assert ch.chart_type != "box", f"Fallback report section '{sec.heading}' should not use box plot on small dataset"


def test_specific_chart_type_strictly_enforced(sample_dataset):
    from backend.agent import DataAgent
    from backend.memory.database import SQLiteMemoryRepository
    from backend.memory.service import MemoryService

    class FakeChartLLM:
        def chat(self, messages, tools=None):
            # Pretend the LLM tried to return BOTH a box plot and a bar chart when the user asked ONLY for a scatter plot
            return {
                "role": "assistant",
                "content": (
                    '{"blocks": ['
                    '{"type": "markdown", "text": "Here is the requested chart."},'
                    '{"type": "chart", "chart": {"chart_type": "box", "title": "Wrong Box", "source": "dataset", "y": "sales"}},'
                    '{"type": "chart", "chart": {"chart_type": "bar", "title": "Wrong Bar", "source": "dataset", "x": "category", "y": "sales"}}'
                    ']}'
                ),
            }

    mem_svc = MemoryService(repository=SQLiteMemoryRepository(":memory:"))
    agent = DataAgent(FakeChartLLM(), memory_service=mem_svc)

    resp, _ = agent.run("Show me a scatter plot of sales vs profit", sample_dataset, [])
    chart_blocks = [b for b in resp.blocks if b.type == "chart"]
    assert len(chart_blocks) == 1
    assert chart_blocks[0].chart.chart_type == "scatter"

