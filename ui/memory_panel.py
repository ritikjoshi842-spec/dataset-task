import html
import importlib
import streamlit as st
import ui.icons
if not hasattr(ui.icons, "MEMORY_ICON"):
    importlib.reload(ui.icons)
from backend.memory import get_memory_service, MemoryType
from ui.icons import MEMORY_ICON, clean_html

MEMORY_TYPE_LABELS: dict[str, str] = {
    "preference": "Preference",
    "domain_knowledge": "Domain Knowledge",
    "correction": "Correction",
    "instruction": "Reusable Instruction",
    "filter_rule": "Filter Rule",
    "insight": "Important Insight",
}


@st.dialog("Persistent AI Memory", width="large")
def memory_dialog():
    mem_svc = get_memory_service()
    status = mem_svc.get_status()

    # 1. Connection & Health Banner
    if status.available:
        status_html = f"""
        <div style="display: flex; align-items: center; justify-content: space-between; background: rgba(16, 185, 129, 0.10); border: 1px solid rgba(16, 185, 129, 0.30); border-radius: 12px; padding: 0.7rem 1rem; margin-bottom: 1rem;">
            <div style="display: flex; align-items: center; gap: 8px;">
                <span style="width: 9px; height: 9px; border-radius: 9999px; background: #10B981; display: inline-block;"></span>
                <span style="font-size: 0.86rem; font-weight: 600; color: var(--text-primary);">{html.escape(status.message)}</span>
            </div>
            <span style="font-size: 0.75rem; color: var(--text-muted);">Cross-session persistence active</span>
        </div>
        """
    else:
        err_detail = html.escape(status.last_error or "Database connection unavailable.")
        status_html = f"""
        <div style="background: rgba(245, 158, 11, 0.12); border: 1px solid rgba(245, 158, 11, 0.38); border-radius: 12px; padding: 0.85rem 1rem; margin-bottom: 1rem;">
            <div style="font-size: 0.88rem; font-weight: 700; color: #F59E0B; margin-bottom: 4px;">
                {html.escape(status.message)}
            </div>
            <div style="font-size: 0.8rem; color: var(--text-secondary); line-height: 1.45;">
                {err_detail}<br/>
                <span style="color: var(--text-muted);">Core dataset analysis, charts, and PDF reports continue to work normally in degraded memory mode.</span>
            </div>
        </div>
        """
    st.markdown(clean_html(status_html), unsafe_allow_html=True)

    st.markdown(
        clean_html(
            "<p style='font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 0.85rem;'>"
            "The AI retains reusable preferences, metric definitions, corrections, and filter rules across sessions. "
            "You can also say <code>\"Remember that net revenue excludes refunded orders\"</code> or "
            "<code>\"Forget my old chart preference\"</code> directly in chat."
            "</p>"
        ),
        unsafe_allow_html=True,
    )

    # 2. Add New Memory Explicitly
    with st.expander("➕ Add a New Persistent Memory", expanded=False):
        with st.form("add_memory_form", clear_on_submit=True):
            col_t, col_top, col_ent = st.columns(3)
            with col_t:
                new_type = st.selectbox(
                    "Memory Type",
                    options=list(MEMORY_TYPE_LABELS.keys()),
                    format_func=lambda k: MEMORY_TYPE_LABELS.get(k, k),
                )
            with col_top:
                new_topic = st.text_input("Topic (optional)", placeholder="e.g. revenue, reporting")
            with col_ent:
                new_entity = st.text_input("Metric / Rule Name (optional)", placeholder="e.g. active_customers")

            new_content = st.text_area(
                "Memory Statement",
                placeholder="e.g. Active customers excludes cancelled accounts.",
                height=75,
            )
            submitted = st.form_submit_button("Save Memory to Database", type="primary", use_container_width=True)
            if submitted:
                rec, msg = mem_svc.add_manual_memory(
                    content=new_content,
                    memory_type=new_type,  # type: ignore[arg-type]
                    topic=new_topic or None,
                    target_entity=new_entity or None,
                )
                if rec:
                    st.success(msg)
                    st.rerun()
                else:
                    st.warning(msg)

    st.divider()

    # 3. List & Manage Stored Memories
    memories = mem_svc.list_memories(include_inactive=True)
    if not memories:
        st.info("No persistent memories stored yet. Add one above or tell the assistant in chat to remember a rule or preference.")
        return

    st.markdown(
        clean_html(
            f"<div style='font-size: 0.88rem; font-weight: 700; color: var(--text-primary); margin-bottom: 0.65rem;'>"
            f"Stored Memories ({len(memories)})"
            f"</div>"
        ),
        unsafe_allow_html=True,
    )

    for mem in memories:
        badge_label = MEMORY_TYPE_LABELS.get(mem.memory_type, mem.memory_type)
        state_badge = "Active" if mem.is_active else "Inactive"
        state_color = "#10B981" if mem.is_active else "#94A3B8"
        meta_parts = [f"Type: {badge_label}"]
        if mem.topic:
            meta_parts.append(f"Topic: {mem.topic}")
        if mem.target_entity:
            meta_parts.append(f"Target: {mem.target_entity}")
        meta_str = " · ".join(meta_parts)

        with st.container():
            st.markdown(
                clean_html(
                    f"""
                    <div style="background: var(--surface-card); border: 1px solid var(--border-subtle); border-radius: 12px; padding: 0.8rem 1rem; margin-bottom: 0.45rem;">
                        <div style="display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 4px;">
                            <span style="font-size: 0.74rem; font-weight: 600; color: var(--accent-primary); text-transform: uppercase; letter-spacing: 0.04em;">
                                {html.escape(meta_str)}
                            </span>
                            <span style="font-size: 0.72rem; font-weight: 700; color: {state_color};">
                                ● {state_badge}
                            </span>
                        </div>
                        <div style="font-size: 0.92rem; font-weight: 500; color: var(--text-primary);">
                            {html.escape(mem.content)}
                        </div>
                    </div>
                    """
                ),
                unsafe_allow_html=True,
            )

            act_c1, act_c2, act_c3 = st.columns([1, 1, 1])
            with act_c1:
                toggle_label = "Deactivate" if mem.is_active else "Activate"
                if st.button(toggle_label, key=f"mem_toggle_{mem.id}", use_container_width=True):
                    mem_svc.set_active(mem.id, not mem.is_active)
                    st.rerun()
            with act_c2:
                edit_key = f"editing_{mem.id}"
                if st.button("Edit", key=f"mem_edit_btn_{mem.id}", use_container_width=True):
                    st.session_state[edit_key] = not st.session_state.get(edit_key, False)
                    st.rerun()
            with act_c3:
                if st.button("Delete", key=f"mem_del_{mem.id}", use_container_width=True):
                    mem_svc.delete_memory(mem.id)
                    st.rerun()

            if st.session_state.get(f"editing_{mem.id}", False):
                with st.form(f"edit_form_{mem.id}"):
                    updated_text = st.text_area("Edit Content", value=mem.content, key=f"edit_txt_{mem.id}")
                    e_c1, e_c2 = st.columns(2)
                    with e_c1:
                        updated_type = st.selectbox(
                            "Type",
                            options=list(MEMORY_TYPE_LABELS.keys()),
                            index=list(MEMORY_TYPE_LABELS.keys()).index(mem.memory_type)
                            if mem.memory_type in MEMORY_TYPE_LABELS
                            else 0,
                            key=f"edit_type_{mem.id}",
                        )
                    with e_c2:
                        updated_entity = st.text_input(
                            "Target Metric / Rule",
                            value=mem.target_entity or "",
                            key=f"edit_ent_{mem.id}",
                        )
                    if st.form_submit_button("Update Memory", type="primary"):
                        mem_svc.edit_memory(
                            memory_id=mem.id,
                            content=updated_text,
                            memory_type=updated_type,  # type: ignore[arg-type]
                            topic=mem.topic,
                            target_entity=updated_entity.strip() or None,
                        )
                        st.session_state[f"editing_{mem.id}"] = False
                        st.rerun()
