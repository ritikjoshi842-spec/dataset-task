import pytest
import pandas as pd
from backend.dataset import clean_and_profile_dataset
from backend.schemas import ChartSpec, ToolResult
from backend.viz.spec import validate_chart_spec
from backend.viz.plotly_engine import render_plotly
from backend.viz.mpl_engine import render_mpl

@pytest.fixture
def sample_ctx():
    df = pd.DataFrame({
        "sales": [100, 200, 300],
        "category": ["A", "B", "A"]
    })
    return clean_and_profile_dataset("test", df)

def test_validate_chart_spec(sample_ctx):
    spec = ChartSpec(
        chart_type="bar",
        title="Test",
        source="dataset",
        x="category",
        y="sales"
    )
    ok, errors, _ = validate_chart_spec(spec, sample_ctx)
    assert ok
    assert len(errors) == 0
    
    # Invalid type
    spec.chart_type = "pie"
    ok, errors, _ = validate_chart_spec(spec, sample_ctx)
    assert not ok
    
    # Invalid column
    spec.chart_type = "bar"
    spec.x = "nonexistent"
    ok, errors, _ = validate_chart_spec(spec, sample_ctx)
    assert not ok
    
def test_render_engines(sample_ctx):
    spec = ChartSpec(
        chart_type="bar",
        title="Test",
        source="dataset",
        x="category",
        y="sales"
    )
    
    fig = render_plotly(spec, sample_ctx)
    assert fig is not None
    
    img_bytes = render_mpl(spec, sample_ctx)
    assert len(img_bytes) > 0
