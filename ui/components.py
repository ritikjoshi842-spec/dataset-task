import streamlit as st
import html
from backend.dataset import DatasetContext
from ui.icons import DATABASE_ICON, clean_html


from ui.memory_panel import memory_dialog


def render_theme_toggle():
    """Renders the fixed top-left circular Light/Dark mode toggle button."""
    current_theme = st.session_state.get("theme", "dark")
    help_text = "Switch to Light Mode" if current_theme == "dark" else "Switch to Dark Mode"
    with st.container(key="theme_toggle_wrap"):
        if st.button("", key="btn_theme_toggle", help=help_text):
            st.session_state.theme = "light" if current_theme == "dark" else "dark"
            st.rerun()


def render_memory_button():
    """Renders the fixed left circular Persistent Memory manager button."""
    with st.container(key="memory_toggle_wrap"):
        if st.button("", key="btn_memory_toggle", help="Manage Persistent AI Memory"):
            memory_dialog()



def render_dataset_summary(ctx: DatasetContext):
    """Renders the dataset summary KPI card and preview."""
    num_cols = sum(1 for c in ctx.schema.values() if c.semantic_type == "numeric")
    cat_cols = sum(1 for c in ctx.schema.values() if c.semantic_type == "categorical")
    date_cols = sum(1 for c in ctx.schema.values() if c.semantic_type == "datetime")
    bool_cols = sum(1 for c in ctx.schema.values() if c.semantic_type == "boolean")

    total_cells = ctx.n_rows * ctx.n_cols if ctx.n_rows > 0 and ctx.n_cols > 0 else 1
    total_null_pct = round((ctx.quality.total_nulls / total_cells) * 100, 1)
    completeness_pct = round(100.0 - total_null_pct, 1)

    card_html = f"""
    <div style="background: var(--surface-card); backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px); border: 1px solid var(--border-subtle); border-radius: 16px; padding: 1.25rem; margin-bottom: 1.25rem; box-shadow: var(--shadow-card); color: var(--text-primary);">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; flex-wrap: wrap; gap: 0.5rem;">
            <div style="display: flex; align-items: center; gap: 0.6rem;">
                <span style="color: var(--accent-primary); display: inline-flex;">{DATABASE_ICON}</span>
                <span style="font-size: 1.05rem; font-weight: 700; color: var(--text-primary);">{html.escape(ctx.name)}</span>
            </div>
            <span style="font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; font-weight: 600; background: var(--table-header-bg); color: var(--accent-primary); padding: 4px 12px; border-radius: 9999px; border: 1px solid var(--border-subtle);">
                {ctx.n_rows:,} rows × {ctx.n_cols} cols
            </span>
        </div>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(115px, 1fr)); gap: 0.65rem; font-size: 0.84rem;">
            <div style="background: var(--surface-button); padding: 0.6rem 0.75rem; border-radius: 10px; border: 1px solid var(--border-subtle);">
                <div style="color: var(--text-muted); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.04em;">Numeric</div>
                <div style="font-weight: 700; font-size: 1rem; color: var(--text-primary); margin-top: 2px;">{num_cols}</div>
            </div>
            <div style="background: var(--surface-button); padding: 0.6rem 0.75rem; border-radius: 10px; border: 1px solid var(--border-subtle);">
                <div style="color: var(--text-muted); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.04em;">Categorical</div>
                <div style="font-weight: 700; font-size: 1rem; color: var(--text-primary); margin-top: 2px;">{cat_cols}</div>
            </div>
            <div style="background: var(--surface-button); padding: 0.6rem 0.75rem; border-radius: 10px; border: 1px solid var(--border-subtle);">
                <div style="color: var(--text-muted); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.04em;">Datetime</div>
                <div style="font-weight: 700; font-size: 1rem; color: var(--text-primary); margin-top: 2px;">{date_cols}</div>
            </div>
            <div style="background: var(--surface-button); padding: 0.6rem 0.75rem; border-radius: 10px; border: 1px solid var(--border-subtle);">
                <div style="color: var(--text-muted); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.04em;">Boolean</div>
                <div style="font-weight: 700; font-size: 1rem; color: var(--text-primary); margin-top: 2px;">{bool_cols}</div>
            </div>
            <div style="background: var(--surface-button); padding: 0.6rem 0.75rem; border-radius: 10px; border: 1px solid var(--border-subtle);">
                <div style="color: var(--text-muted); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.04em;">Completeness</div>
                <div style="font-weight: 700; font-size: 1rem; color: #10B981; margin-top: 2px;">{completeness_pct}%</div>
            </div>
            <div style="background: var(--surface-button); padding: 0.6rem 0.75rem; border-radius: 10px; border: 1px solid var(--border-subtle);">
                <div style="color: var(--text-muted); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.04em;">Duplicates</div>
                <div style="font-weight: 700; font-size: 1rem; color: var(--text-primary); margin-top: 2px;">{ctx.quality.duplicates:,}</div>
            </div>
        </div>
    </div>
    """
    st.markdown(clean_html(card_html), unsafe_allow_html=True)

    if ctx.quality.high_null_cols or ctx.quality.constant_cols:
        issues = []
        if ctx.quality.high_null_cols:
            issues.append(f"High nulls (>50%): {', '.join(ctx.quality.high_null_cols)}")
        if ctx.quality.constant_cols:
            issues.append(f"Constant columns: {', '.join(ctx.quality.constant_cols)}")
        st.info("Detected dataset characteristics: " + " | ".join(issues))

    with st.expander("Preview First 10 Rows", expanded=False):
        st.dataframe(ctx.df.head(10), use_container_width=True, hide_index=True)


def render_error_banner(message: str):
    """Renders a styled error banner with an inline SVG alert icon."""
    err_html = f"""
    <div style="display: flex; align-items: center; gap: 0.65rem; background: rgba(239, 68, 68, 0.12); border: 1px solid rgba(239, 68, 68, 0.35); border-radius: 12px; padding: 0.85rem 1.1rem; color: #EF4444; margin: 0.6rem 0; font-size: 0.9rem; font-weight: 500;">
        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0;"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
        <span>{html.escape(message)}</span>
    </div>
    """
    st.markdown(clean_html(err_html), unsafe_allow_html=True)
