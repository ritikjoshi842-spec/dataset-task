import html
import streamlit as st
from backend.dataset import load_dataset_from_bytes
from backend.report.builder import generate_report_draft
from backend.report.pdf import build_pdf_report
from ui.icons import DATABASE_ICON, clean_html
from ui.components import render_dataset_summary


@st.dialog("Upload Tabular Dataset")
def upload_dialog():
    st.markdown(
        clean_html(
            "<p style='color: var(--text-secondary); font-size: 0.92rem; margin-bottom: 0.75rem;'>"
            "Select a <b>CSV</b> or <b>Excel</b> (<code>.xlsx</code>, <code>.xls</code>) file to profile its schema and start analyzing."
            "</p>"
        ),
        unsafe_allow_html=True,
    )
    uploaded_file = st.file_uploader(
        "Choose a file",
        type=["csv", "xlsx", "xls"],
        label_visibility="collapsed",
    )

    sheet_name = None
    if uploaded_file is not None:
        ext = uploaded_file.name.split(".")[-1].lower()
        if ext in ["xlsx", "xls"]:
            import openpyxl

            try:
                wb = openpyxl.load_workbook(uploaded_file, read_only=True)
                sheets = wb.sheetnames
                if len(sheets) > 1:
                    sheet_name = st.selectbox("Select Excel Sheet", sheets)
                uploaded_file.seek(0)
            except Exception:
                uploaded_file.seek(0)

        if st.button("Process & Load Dataset", type="primary", use_container_width=True):
            with st.spinner("Profiling dataset & inferring schema..."):
                try:
                    file_bytes = uploaded_file.read()
                    ctx = load_dataset_from_bytes(
                        name=uploaded_file.name,
                        file_bytes=file_bytes,
                        extension=ext,
                        sheet_name=sheet_name,
                    )
                    st.session_state.dataset = ctx
                    # Reset chat & reports on new dataset upload
                    st.session_state.messages = []
                    st.session_state.llm_history = []
                    st.session_state.tool_results = {}
                    st.session_state.report_cache = {}
                    st.success(f"Loaded {ctx.name} ({ctx.n_rows:,} rows × {ctx.n_cols} columns)")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to load dataset: {str(e)}")

    if st.session_state.dataset is not None:
        st.divider()
        render_dataset_summary(st.session_state.dataset)
        if st.button("Open Analytical Chat", type="primary", use_container_width=True):
            st.session_state.view = "chat"
            st.rerun()


def render_landing_view():
    ds = st.session_state.dataset

    # Professional Hero Section (No bottom-right Gemini logo)
    hero_html = """
    <div style="text-align: center; margin-top: 10vh; max-width: 780px; margin-left: auto; margin-right: auto; padding: 0 1rem;">
        <div style="display: inline-flex; align-items: center; gap: 8px; padding: 6px 16px; border-radius: 9999px; background: var(--surface-card); border: 1px solid var(--border-subtle); box-shadow: var(--shadow-btn); margin-bottom: 1.5rem;">
            <span style="width: 8px; height: 8px; border-radius: 9999px; background: #10B981; display: inline-block;"></span>
            <span style="font-size: 0.75rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--text-secondary);">Agentic Tabular Intelligence</span>
        </div>
        <div style="font-size: clamp(1rem, 2vw, 1.25rem); color: var(--text-secondary); font-weight: 500; letter-spacing: 0.01em; margin-bottom: 0.35rem;">
            Hey, I'm Ritik! Welcome to my
        </div>
        <h1 style="font-size: clamp(2.4rem, 6vw, 4.4rem); font-weight: 800; letter-spacing: -0.03em; line-height: 1.1; margin: 0.2rem 0 1rem 0; background: var(--hero-title-gradient); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;">
            DATA ANALYTICS TOOL
        </h1>
        <p style="font-size: clamp(0.95rem, 1.5vw, 1.08rem); color: var(--text-muted); max-width: 580px; margin: 0 auto 2rem auto; line-height: 1.6; font-weight: 400;">
            Upload any CSV or Excel workbook to run verified statistical computations, converse with your data in plain English, and export executive PDF reports.
        </p>
    </div>
    """
    st.markdown(clean_html(hero_html), unsafe_allow_html=True)

    # Active Dataset Card (if loaded)
    if ds is not None:
        total_cells = ds.n_rows * ds.n_cols if ds.n_rows > 0 and ds.n_cols > 0 else 1
        completeness = round(100.0 - (ds.quality.total_nulls / total_cells) * 100, 1)
        ds_card_html = f"""
        <div style="max-width: 540px; margin: 0.5rem auto 2rem auto; background: var(--surface-card); backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px); padding: 1rem 1.35rem; border-radius: 18px; border: 1px solid var(--border-strong); box-shadow: var(--shadow-card); display: flex; align-items: center; justify-content: space-between; gap: 1rem; flex-wrap: wrap;">
            <div style="display: flex; align-items: center; gap: 0.75rem;">
                <div style="width: 40px; height: 40px; border-radius: 12px; background: var(--table-header-bg); color: var(--accent-primary); display: flex; align-items: center; justify-content: center;">
                    {DATABASE_ICON}
                </div>
                <div style="text-align: left;">
                    <div style="font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-muted); font-weight: 600;">Active Dataset Ready</div>
                    <div style="font-size: 0.98rem; font-weight: 700; color: var(--text-primary);">{html.escape(ds.name)}</div>
                </div>
            </div>
            <div style="display: flex; align-items: center; gap: 0.5rem;">
                <span style="font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; font-weight: 600; padding: 5px 11px; border-radius: 9999px; background: var(--surface-button); color: var(--text-primary); border: 1px solid var(--border-subtle);">
                    {ds.n_rows:,} × {ds.n_cols}
                </span>
                <span style="font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; font-weight: 600; padding: 5px 11px; border-radius: 9999px; background: rgba(16, 185, 129, 0.12); color: #10B981; border: 1px solid rgba(16, 185, 129, 0.28);">
                    {completeness}% complete
                </span>
            </div>
        </div>
        """
        st.markdown(clean_html(ds_card_html), unsafe_allow_html=True)

    # Bottom Floating Glass Dock with Circular Icon Buttons
    with st.container(key="bottom_dock"):
        dock_col1, dock_col2, dock_col3 = st.columns([1, 1, 1])

        with dock_col1:
            if st.button("", key="btn_upload_dock", help="Upload CSV or Excel Dataset"):
                upload_dialog()

        with dock_col2:
            has_ds = ds is not None
            if st.button(
                "",
                key="btn_ask_dock",
                help="Ask questions about your dataset" if has_ds else "Upload a dataset first",
            ):
                if has_ds:
                    st.session_state.view = "chat"
                    st.rerun()
                else:
                    st.toast("Please upload a dataset first using the Upload button.", icon="ℹ️")

        with dock_col3:
            if ds is not None:
                cached_pdf = st.session_state.report_cache.get(ds.fingerprint)
                if cached_pdf:
                    st.download_button(
                        label="",
                        data=cached_pdf,
                        file_name=f"{ds.name}_analysis_report.pdf",
                        mime="application/pdf",
                        key="btn_download_cached",
                        help="Download Verified PDF Analysis Report",
                    )
                else:
                    if st.button(
                        "",
                        key="btn_gen_report",
                        help="Generate Verified PDF Analysis Report",
                    ):
                        with st.spinner("Generating verified PDF report..."):
                            from backend.llm_client import LLMClient

                            llm = LLMClient()
                            draft, t_res = generate_report_draft(ds, llm)
                            pdf_bytes = build_pdf_report(draft, ds, t_res)
                            st.session_state.report_cache[ds.fingerprint] = pdf_bytes
                            st.rerun()
            else:
                if st.button(
                    "",
                    key="btn_download_disabled",
                    help="Upload a dataset first to generate a PDF report",
                ):
                    st.toast("Please upload a dataset first using the Upload button.", icon="ℹ️")
