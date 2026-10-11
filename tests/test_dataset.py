import pytest
import pandas as pd
from backend.dataset import clean_and_profile_dataset, infer_semantic_type

def test_infer_semantic_type_numeric():
    # standard numeric
    s = pd.Series([1, 2, 3, 4, 5])
    assert infer_semantic_type("test", s, 5) == "numeric"

    # currency strings
    s = pd.Series(["$1.00", "$2.50", "$3,000", "$4", "NaN"])
    assert infer_semantic_type("test", s, 5) == "numeric"
    
def test_infer_semantic_type_datetime():
    # standard datetime
    s = pd.Series(pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-03"]))
    assert infer_semantic_type("test", s, 3) == "datetime"
    
    # string dates
    s = pd.Series(["01/12/2020", "02/12/2020", "03/12/2020"])
    assert infer_semantic_type("test", s, 3) == "datetime"
    
def test_infer_semantic_type_boolean():
    s = pd.Series(["Yes", "No", "yes", "no", "YES", None])
    assert infer_semantic_type("test", s, 6) == "boolean"

def test_infer_semantic_type_id_like():
    s = pd.Series(["ID001", "ID002", "ID003", "ID004", "ID005"])
    assert infer_semantic_type("employee_id", s, 5) == "id_like"

def test_clean_and_profile_dataset():
    df = pd.DataFrame({
        "  Sales  ": ["$1,000", "$2,000", "$3,000", "$4,000", "$5,000", None],
        "Date": ["2023-01-01", "2023-01-02", "2023-01-03", "2023-01-04", "2023-01-05", "2023-01-06"],
        "Category": ["A", "B", "A", "B", "C", "C"],
        "Active": ["Yes", "No", "Yes", "Yes", "No", "No"]
    })
    
    ctx = clean_and_profile_dataset("test_ds", df)
    
    assert "Sales" in ctx.schema
    assert ctx.schema["Sales"].semantic_type == "numeric"
    assert ctx.schema["Date"].semantic_type == "datetime"
    assert ctx.schema["Category"].semantic_type == "categorical"
    assert ctx.schema["Active"].semantic_type == "boolean"
    
    assert ctx.n_rows == 6
    assert ctx.n_cols == 4
    
    # ensure dataframe was cleaned
    assert pd.api.types.is_numeric_dtype(ctx.df["Sales"])
    assert pd.api.types.is_datetime64_any_dtype(ctx.df["Date"])
