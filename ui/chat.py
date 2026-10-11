import html
import streamlit as st
import pandas as pd
import json
from backend.dataset import DatasetContext
from backend.agent import DataAgent
from backend.llm_client import LLMClient
from backend.schemas import AgentResponse, Block
from backend.viz.plotly_engine import render_plotly
from ui.icons import ASK_AI_ICON, DATABASE_ICON, clean_html
from ui.components import render_error_banner


def get_suggested_questions(ctx: DatasetContext) -> list[str]:
    """Generates 4 dynamic question chips based on the schema."""
    num_cols = [c for c, info in ctx.schema.items() if info.semantic_type == "numeric"]
    cat_cols = [c for c, info in ctx.schema.items() if info.semantic_type == "categorical"]
    date_cols = [c for c, info in ctx.schema.items() if info.semantic_type == "datetime"]

    chips = ["Summarise this dataset in plain English"]
    if num_cols and cat_cols:
        chips.append(f"Compare average {num_cols[0]} across {cat_cols[0]}")
        chips.append(f"Plot a bar chart of {num_cols[0]} by {cat_cols[0]}")
    elif date_cols and num_cols:
        chips.append(f"How did {num_cols[0]} change over time?")
        chips.append(f"Plot a line chart of {num_cols[0]} over time")
    elif len(num_cols) >= 2:
        chips.append(f"What relationships exist between {num_cols[0]} and {num_cols[1]}?")
    if num_cols and len(chips) < 4:
        chips.append(f"Are there any unusual outliers in {num_cols[0]}?")

    return chips[:4]


def render_block(block: Block, ctx: DatasetContext, tool_results: dict, block_idx: str):
    """Renders a single block in the order specified by the agent."""
    if block.type == "markdown" and block.text:
        st.markdown(block.text)

    elif block.type == "chart" and block.chart:
        try:
            current_theme = st.session_state.get("theme", "dark")
            fig = render_plotly(block.chart, ctx, tool_results, theme=current_theme)
            if fig:
                chart_col, _ = st.columns([6, 4])
                with chart_col:
                    st.plotly_chart(
                        fig,
                        use_container_width=True,
                        key=f"chart_{block_idx}_{block.chart.title}",
                        config={
                            "displayModeBar": "hover",
                            "displaylogo": False,
                            "modeBarButtonsToRemove": [
                                "lasso2d",
                                "select2d",
                                "autoScale2d",
                                "zoomIn2d",
                                "zoomOut2d",
                            ],
                        },
                    )
            else:
                st.warning(f"Unable to render chart: {block.chart.title}")
        except Exception as e:
            st.warning(f"Couldn't render chart '{block.chart.title}': {str(e)}")

    elif block.type == "table":
        table_data = None
        if block.table_ref and block.table_ref in tool_results:
            tr = tool_results[block.table_ref]
            table_data = tr.table
        elif tool_results:
            # Fallback to most recent tool result with a table
            for tr in reversed(list(tool_results.values())):
                if tr.table:
                    table_data = tr.table
                    break

        if table_data:
            df_table = pd.DataFrame(table_data)
            if block.caption:
                st.caption(block.caption)
            with st.expander(
                f"View Underlying Data Table ({len(df_table)} rows)",
                expanded=len(df_table) <= 8,
            ):
                st.dataframe(df_table, use_container_width=True, hide_index=True)
                csv_data = df_table.to_csv(index=False).encode("utf-8")
                st.download_button(
                    label="Download Table (CSV)",
                    data=csv_data,
                    file_name="query_results.csv",
                    mime="text/csv",
                    key=f"csv_dl_{block_idx}",
                )


def render_chat_view():
    ctx: DatasetContext = st.session_state.dataset
    if ctx is None:
        st.warning("No dataset currently active. Please return to the home screen to upload a dataset.")
        if st.button("Return to Home"):
            st.session_state.view = "landing"
            st.rerun()
        return

    # Top Workspace Header Bar
    header_col1, header_col2 = st.columns([11, 1])
    with header_col1:
        header_html = f"""
        <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; background: var(--surface-card); backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px); border: 1px solid var(--border-subtle); border-radius: 16px; padding: 0.75rem 1.15rem; box-shadow: var(--shadow-card);">
            <div style="display: flex; align-items: center; gap: 12px;">
                <div style="background: var(--accent-gradient); color: #FFFFFF; border-radius: 12px; width: 38px; height: 38px; display: flex; align-items: center; justify-content: center; box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3);">
                    {ASK_AI_ICON}
                </div>
                <div>
                    <div style="margin: 0; font-size: 1.05rem; font-weight: 700; color: var(--text-primary); line-height: 1.2;">Analytical Assistant</div>
                    <div style="font-size: 0.78rem; color: var(--text-muted); margin-top: 2px;">Verified Python / Pandas execution</div>
                </div>
            </div>
            <div style="display: inline-flex; align-items: center; gap: 8px; background: var(--surface-button); border: 1px solid var(--border-subtle); border-radius: 9999px; padding: 5px 13px; font-size: 0.8rem; color: var(--text-secondary);">
                <span style="color: var(--accent-primary); display: inline-flex;">{DATABASE_ICON}</span>
                <span style="font-weight: 600; color: var(--text-primary);">{html.escape(ctx.name)}</span>
                <span style="font-family: 'JetBrains Mono', monospace; font-size: 0.74rem; color: var(--text-muted);">({ctx.n_rows:,} × {ctx.n_cols})</span>
            </div>
        </div>
        """
        st.markdown(clean_html(header_html), unsafe_allow_html=True)
    with header_col2:
        if st.button("", key="btn_back_home", help="Return to Home"):
            st.session_state.view = "landing"
            st.rerun()

    st.markdown("<div style='height: 1rem;'></div>", unsafe_allow_html=True)

    # Empty State (if no messages yet)
    if not st.session_state.messages:
        empty_html = f"""
        <div style="text-align: center; margin: 2rem auto 1.5rem auto; max-width: 620px; background: var(--surface-card); backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px); border: 1px solid var(--border-subtle); border-radius: 20px; padding: 2rem 1.75rem; box-shadow: var(--shadow-card);">
            <div style="width: 48px; height: 48px; margin: 0 auto 1rem auto; border-radius: 9999px; background: var(--accent-gradient); color: #FFFFFF; display: flex; align-items: center; justify-content: center; box-shadow: 0 8px 20px rgba(37, 99, 235, 0.32);">
                {ASK_AI_ICON}
            </div>
            <div style="font-size: 1.25rem; font-weight: 700; color: var(--text-primary); margin-bottom: 0.5rem;">
                Ask anything about {html.escape(ctx.name)}
            </div>
            <div style="color: var(--text-secondary); font-size: 0.92rem; line-height: 1.6;">
                Ask questions in plain English—every statistic is computed directly on your dataset using Pandas and NumPy.<br/>
                <span style="font-size: 0.8rem; color: var(--text-muted);">Charts are only generated when you explicitly ask to plot or visualize data.</span>
            </div>
        </div>
        """
        st.markdown(clean_html(empty_html), unsafe_allow_html=True)

        # Suggested chips
        chips = get_suggested_questions(ctx)
        if chips:
            st.markdown(
                "<div style='text-align: center; font-size: 0.78rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-muted); margin-bottom: 0.65rem;'>Suggested Queries</div>",
                unsafe_allow_html=True,
            )
            chip_cols = st.columns(len(chips))
            for i, chip in enumerate(chips):
                with chip_cols[i]:
                    if st.button(chip, key=f"chip_{i}", use_container_width=True):
                        st.session_state.pending_prompt = chip
                        st.rerun()

    # Render Conversation History
    for idx, msg in enumerate(st.session_state.messages):
        role = msg["role"]
        with st.chat_message(role):
            if role == "user":
                st.markdown(msg["content"])
            else:
                resp: AgentResponse = msg.get("response")
                if resp:
                    for b_idx, block in enumerate(resp.blocks):
                        render_block(block, ctx, st.session_state.tool_results, f"{idx}_{b_idx}")

                    if resp.warnings:
                        for warn in resp.warnings:
                            st.caption(f"Note: {warn}")

                    if resp.tool_trace:
                        with st.expander("View Computation Trace", expanded=False):
                            for tr in resp.tool_trace:
                                status_label = "OK" if tr.ok else "ERR"
                                st.markdown(f"**[{status_label}] Tool: `{tr.name}`** ({tr.duration_ms} ms)")
                                st.caption(f"Summary: {tr.summary}")
                                st.json(tr.args)
                elif "content" in msg:
                    st.markdown(msg["content"])

    # Handle pending prompt from chips
    prompt_to_handle = None
    if getattr(st.session_state, "pending_prompt", None):
        prompt_to_handle = st.session_state.pending_prompt
        st.session_state.pending_prompt = None

    # Chat Input
    user_input = st.chat_input("Ask a question about your data (or ask to plot a chart)...")
    if user_input or prompt_to_handle:
        query = user_input or prompt_to_handle

        # Append User Message
        st.session_state.messages.append({"role": "user", "content": query})
        with st.chat_message("user"):
            st.markdown(query)

        # Run Agent
        with st.chat_message("assistant"):
            with st.status("Analyzing your dataset...", expanded=True) as status_box:
                try:
                    llm = LLMClient()
                    agent = DataAgent(llm)

                    status_box.write("Running calculations with Pandas & NumPy...")
                    agent_resp, new_tools = agent.run(
                        user_question=query,
                        ctx=ctx,
                        history=st.session_state.llm_history,
                    )

                    # Update tool results in session state
                    st.session_state.tool_results.update(new_tools)

                    # Update history
                    st.session_state.llm_history.append({"role": "user", "content": query})
                    st.session_state.llm_history.append(
                        {
                            "role": "assistant",
                            "content": json.dumps(
                                [b.model_dump() for b in agent_resp.blocks], default=str
                            ),
                        }
                    )

                    status_box.update(label="Analysis complete", state="complete", expanded=False)

                    # Save Assistant Message
                    st.session_state.messages.append({"role": "assistant", "response": agent_resp})
                    st.rerun()

                except Exception as e:
                    status_box.update(label="Analysis encountered an error", state="error", expanded=True)
                    error_msg = str(e)
                    render_error_banner(f"Could not complete analysis: {error_msg}")
                    st.session_state.messages.append(
                        {
                            "role": "assistant",
                            "content": f"**Error encountered:** {error_msg}\n\nPlease verify that your API key is configured or try rephrasing your question.",
                        }
                    )
