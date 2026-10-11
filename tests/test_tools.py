import pytest
import pandas as pd
from backend.dataset import clean_and_profile_dataset
from backend.tools.filter_data import FilterDataTool, FilterDataArgs
from backend.schemas import Condition
from backend.tools.statistical_analysis import StatisticalAnalysisTool, StatisticalAnalysisArgs

@pytest.fixture
def sample_dataset():
    df = pd.DataFrame({
        "sales": [100, 200, 300, 400, 500, 10000],
        "date": ["2023-01-01", "2023-01-02", "2023-01-03", "2023-01-04", "2023-01-05", "2023-01-06"],
        "category": ["A", "B", "A", "B", "C", "C"],
        "region": ["North", "South", "East", "West", "North", "South"]
    })
    return clean_and_profile_dataset("test", df)

def test_filter_data(sample_dataset):
    tool = FilterDataTool()
    args = FilterDataArgs(
        conditions=[Condition(column="sales", operator=">=", value=300)],
        logic="and"
    )
    res = tool._execute(sample_dataset, args)
    assert res.ok
    assert res.data["total_matches"] == 4
    
def test_statistical_analysis(sample_dataset):
    tool = StatisticalAnalysisTool()
    args = StatisticalAnalysisArgs(columns=["sales"], statistics=["mean", "median", "max"])
    res = tool._execute(sample_dataset, args)
    assert res.ok
    assert "sales" in res.data
    assert res.data["sales"]["mean"] > 0
    assert res.data["sales"]["max"] == 10000
