import pytest
from pathlib import Path
from streamlit.testing.v1 import AppTest
import pandas as pd
from backend.dataset import clean_and_profile_dataset

APP_PATH = str(Path(__file__).resolve().parent.parent / "app.py")

def test_ui_landing_smoke():
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception
    # View starts as landing
    assert at.session_state.view == "landing"
    for md in at.markdown:
        # Ensure no line has 4+ leading spaces that would trigger CommonMark code blocks
        for line in md.value.splitlines():
            assert not line.startswith("    "), f"Indented line in markdown: {line!r}"
    
def test_ui_chat_view_smoke():
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    
    # Inject dataset into session state
    df = pd.DataFrame({"age": [25, 30, 35], "salary": [50000, 60000, 70000], "dept": ["HR", "IT", "IT"]})
    ctx = clean_and_profile_dataset("test_emp", df)
    at.session_state.dataset = ctx
    at.session_state.view = "chat"
    
    at.run()
    assert not at.exception
    assert at.session_state.view == "chat"
    for md in at.markdown:
        for line in md.value.splitlines():
            assert not line.startswith("    "), f"Indented line in markdown: {line!r}"

def test_ui_theme_toggle():
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception
    assert at.session_state.theme == "dark"

    # Click the left theme toggle button
    at.button(key="btn_theme_toggle").click().run()
    assert not at.exception
    assert at.session_state.theme == "light"

    # Toggle back to dark
    at.button(key="btn_theme_toggle").click().run()
    assert not at.exception
    assert at.session_state.theme == "dark"

