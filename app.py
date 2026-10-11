import importlib
import streamlit as st

# Import and reload modules sequentially in bottom-up dependency order
# so an already-running Streamlit server picks up all newly added symbols immediately.
for _mod_name in (
    "backend.config",
    "backend.schemas",
    "ui.icons",
    "backend.viz.spec",
    "backend.tools.statistical_analysis",
    "backend.tools.outlier_detection",
    "backend.tools.correlation_analysis",
    "backend.tools",
    "backend.memory.models",
    "backend.memory.database",
    "backend.memory.selector",
    "backend.memory.retriever",
    "backend.memory.service",
    "backend.memory",
    "backend.viz.plotly_engine",
    "backend.viz.mpl_engine",
    "backend.report.prompts",
    "backend.report.pdf",
    "backend.report.builder",
    "backend.agent",
    "ui.styles",
    "ui.memory_panel",
    "ui.components",
    "ui.landing",
    "ui.chat",
):
    _mod = importlib.import_module(_mod_name)
    try:
        importlib.reload(_mod)
    except Exception:
        pass

import ui.components
from ui.styles import inject_styles
from ui.landing import render_landing_view
from ui.chat import render_chat_view


def render_theme_toggle():
    """Renders the fixed top-left circular Light/Dark mode toggle button."""
    if hasattr(ui.components, "render_theme_toggle"):
        return ui.components.render_theme_toggle()
    current_theme = st.session_state.get("theme", "dark")
    help_text = "Switch to Light Mode" if current_theme == "dark" else "Switch to Dark Mode"
    with st.container(key="theme_toggle_wrap"):
        if st.button("", key="btn_theme_toggle", help=help_text):
            st.session_state.theme = "light" if current_theme == "dark" else "dark"
            st.rerun()


def render_memory_button():
    """Renders the fixed left circular Persistent Memory manager button."""
    if hasattr(ui.components, "render_memory_button"):
        return ui.components.render_memory_button()


def init_state():
    if "view" not in st.session_state:
        st.session_state.view = "landing"
    if "theme" not in st.session_state:
        st.session_state.theme = "dark"
    if "dataset" not in st.session_state:
        st.session_state.dataset = None
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "llm_history" not in st.session_state:
        st.session_state.llm_history = []
    if "tool_results" not in st.session_state:
        st.session_state.tool_results = {}
    if "report_cache" not in st.session_state:
        st.session_state.report_cache = {}
    if "error" not in st.session_state:
        st.session_state.error = None


def main():
    st.set_page_config(
        page_title="Data Analytics Tool",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    init_state()
    inject_styles()
    render_theme_toggle()
    render_memory_button()

    if st.session_state.view == "landing":
        render_landing_view()
    elif st.session_state.view == "chat":
        render_chat_view()


if __name__ == "__main__":
    main()
