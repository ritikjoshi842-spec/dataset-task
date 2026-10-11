import json
from typing import Dict, Any, List, Optional
from backend.dataset import DatasetContext
from backend.schemas import ReportDraft, ReportSection, Finding, ChartSpec, ToolResult
from backend.tools import get_tool
from backend.report.prompts import REPORT_SYSTEM_PROMPT
from backend.llm_client import LLMClient
from backend.viz.spec import (
    validate_chart_spec,
    adapt_chart_for_dataset,
    analyze_dataset_chart_profile,
    curate_report_charts,
    detect_requested_chart_types,
)
from backend.memory import MemoryService, get_memory_service


def _tag_suggested_charts(res: ToolResult, result_key: str):
    if res and res.suggested_charts:
        for sc in res.suggested_charts:
            if sc.source == "tool_result":
                sc.tool_result_id = result_key


def build_report_evidence(
    ctx: DatasetContext,
    session_tools: Optional[Dict[str, ToolResult]] = None,
    memory_service: Optional[MemoryService] = None,
    user_question: Optional[str] = None,
) -> tuple[Dict[str, Any], Dict[str, ToolResult], List[str]]:
    mem_svc = memory_service or get_memory_service()
    relevant_memories, _, tool_hints = mem_svc.retrieve_for_task(
        query=user_question or "comprehensive report summary",
        ctx=ctx,
        task_type="report",
        wants_chart=True,
    )
    preferred_agg = tool_hints.get("preferred_agg_func") or "mean"
    preferred_freq = tool_hints.get("preferred_time_freq")

    sample_rows = ctx.df.head(3).to_dict(orient="records")
    evidence = {
        "dataset_name": ctx.name,
        "n_rows": ctx.n_rows,
        "n_cols": ctx.n_cols,
        "columns": {
            k: {
                "type": v.semantic_type,
                "null_pct": round(v.null_pct, 2),
                "nunique": v.nunique,
                "examples": v.sample_values[:3],
            }
            for k, v in ctx.schema.items()
        },
        "sample_records": sample_rows,
        "quality": {
            "duplicates": ctx.quality.duplicates,
            "total_nulls": ctx.quality.total_nulls,
            "high_null_cols": ctx.quality.high_null_cols,
            "constant_cols": ctx.quality.constant_cols
        },
        "persistent_memories_applied": [m.content for m in relevant_memories],
        "tool_results": {}
    }

    tool_results = dict(session_tools or {})
    not_performed = []

    num_cols = [c for c, info in ctx.schema.items() if info.semantic_type == "numeric"]
    cat_cols = [c for c, info in ctx.schema.items() if info.semantic_type == "categorical"]
    date_cols = [c for c, info in ctx.schema.items() if info.semantic_type == "datetime"]

    # 1. Statistical Analysis
    if num_cols:
        target_num = num_cols[:8]
        stats_tool = get_tool("statistical_analysis")
        res = stats_tool.run(ctx, columns=target_num)
        _tag_suggested_charts(res, "report_stats")
        tool_results["report_stats"] = res
        evidence["tool_results"]["statistical_analysis"] = res.data
    else:
        not_performed.append("Descriptive statistics: No numeric columns found.")

    # 2. Aggregations (up to 3 pairs, honoring preferred_agg from memory)
    if num_cols and cat_cols:
        agg_tool = get_tool("aggregate_data")
        agg_pairs = []
        for i in range(min(3, len(cat_cols))):
            c_col = cat_cols[i]
            n_col = num_cols[i % len(num_cols)]
            t_key = f"report_agg_{i}"
            agg_res = agg_tool.run(
                ctx,
                group_by=[c_col],
                aggregations=[{"column": n_col, "function": preferred_agg}],
                top_n=10,
            )
            _tag_suggested_charts(agg_res, t_key)
            tool_results[t_key] = agg_res
            agg_pairs.append({
                "group_by": c_col,
                "metric": n_col,
                "aggregation_function": preferred_agg,
                "summary": agg_res.summary,
                "table_sample": agg_res.table[:5] if agg_res.table else []
            })
        evidence["tool_results"]["aggregations"] = agg_pairs
    else:
        not_performed.append("Group aggregations: Lacking numeric or categorical columns.")

    # 3. Correlation Analysis
    if len(num_cols) >= 2:
        corr_tool = get_tool("correlation_analysis")
        c_res = corr_tool.run(ctx, columns=num_cols[:10])
        _tag_suggested_charts(c_res, "report_corr")
        tool_results["report_corr"] = c_res
        evidence["tool_results"]["correlation_analysis"] = {
            "summary": c_res.summary,
            "top_pairs": c_res.table[:5] if c_res.table else []
        }
    else:
        not_performed.append("Correlation analysis: Requires at least 2 numeric columns.")

    # 4. Outlier Detection
    if num_cols:
        out_tool = get_tool("outlier_detection")
        o_res = out_tool.run(ctx, columns=num_cols[:6])
        _tag_suggested_charts(o_res, "report_outliers")
        tool_results["report_outliers"] = o_res
        evidence["tool_results"]["outlier_detection"] = o_res.data
    else:
        not_performed.append("Outlier detection: No numeric columns found.")

    # 5. Time Series Analysis
    if date_cols and num_cols:
        ts_tool = get_tool("time_series_analysis")
        ts_kwargs = {
            "date_column": date_cols[0],
            "value_columns": [num_cols[0]],
            "aggregation": "sum",
        }
        if preferred_freq:
            ts_kwargs["frequency"] = preferred_freq
        ts_res = ts_tool.run(ctx, **ts_kwargs)
        _tag_suggested_charts(ts_res, "report_ts")
        tool_results["report_ts"] = ts_res
        evidence["tool_results"]["time_series_analysis"] = {
            "summary": ts_res.summary,
            "metrics": ts_res.data
        }
    else:
        not_performed.append("Time series analysis: No date column found in dataset.")

    return evidence, tool_results, not_performed


def _build_default_plain_english_guide(ctx: DatasetContext, tool_results: Dict[str, ToolResult]) -> str:
    """Creates a warm, non-technical plain-English guide explaining what the dataset is about and what it tells us."""
    num_cols = [c for c, info in ctx.schema.items() if info.semantic_type == "numeric"]
    cat_cols = [c for c, info in ctx.schema.items() if info.semantic_type == "categorical"]
    date_cols = [c for c, info in ctx.schema.items() if info.semantic_type == "datetime"]
    id_cols = [c for c, info in ctx.schema.items() if info.semantic_type == "id_like"]

    parts = [
        f"Think of the '{ctx.name}' dataset as a structured digital spreadsheet containing {ctx.n_rows:,} individual entries (rows), "
        f"where each entry is described by {ctx.n_cols} different pieces of information (columns)."
    ]

    if id_cols:
        parts.append(
            f"Each row represents a unique record identified by '{id_cols[0]}'."
        )
    if cat_cols:
        cat_preview = ", ".join(f"'{c}'" for c in cat_cols[:4])
        parts.append(
            f"It groups records into everyday categories such as {cat_preview}, which helps us compare how different groups perform."
        )
    if num_cols:
        num_preview = ", ".join(f"'{c}'" for c in num_cols[:4])
        parts.append(
            f"It tracks measurable numbers like {num_preview}, allowing us to calculate averages, typical ranges, and spot unusually high or low values."
        )
    if date_cols:
        parts.append(
            f"Because it includes time information ('{date_cols[0]}'), we can also trace how these numbers rise or fall over time."
        )

    # Add a plain-English inference takeaway from the tools
    takeaways = []
    if "report_stats" in tool_results and tool_results["report_stats"].ok:
        for col, st_data in list(tool_results["report_stats"].data.items())[:2]:
            if isinstance(st_data, dict) and "mean" in st_data and "median" in st_data:
                takeaways.append(
                    f"for '{col}', the typical (average) value is around {st_data['mean']:.2f} (with a middle/median value of {st_data['median']:.2f})"
                )
    if "report_corr" in tool_results and tool_results["report_corr"].ok and tool_results["report_corr"].table:
        top_p = tool_results["report_corr"].table[0]
        takeaways.append(
            f"'{top_p.get('feature1')}' and '{top_p.get('feature2')}' show a {top_p.get('strength')} relationship (correlation of {top_p.get('correlation')})"
        )

    if takeaways:
        parts.append(
            "In simple terms, looking across all records tells us that " + "; and ".join(takeaways) + "."
        )

    total_cells = max(ctx.n_rows * ctx.n_cols, 1)
    completeness = 100.0 - ((ctx.quality.total_nulls / total_cells) * 100.0)
    parts.append(
        f"Overall, the dataset is {completeness:.1f}% complete, giving us a solid foundation for the detailed insights that follow."
    )

    return " ".join(parts)


def build_template_fallback_report(ctx: DatasetContext, evidence: Dict[str, Any], not_performed: List[str], tool_results: Dict[str, ToolResult]) -> ReportDraft:
    """Deterministic fallback report without calling LLM."""
    plain_guide = _build_default_plain_english_guide(ctx, tool_results)
    sections = []

    # 1. Plain-English Overview Section
    sections.append(ReportSection(
        heading="1. Understanding the Dataset Structure & Quality",
        body_markdown=(
            f"This dataset ('{ctx.name}') captures {ctx.n_rows:,} total records across {ctx.n_cols} attributes. "
            f"Out of all data cells, {ctx.quality.total_nulls:,} values are blank/missing, and there are "
            f"{ctx.quality.duplicates:,} exact duplicate rows."
        ),
        findings=[
            Finding(
                statement=f"The dataset contains {ctx.n_rows:,} rows and {ctx.n_cols} columns.",
                evidence="Verified from dataset profile"
            )
        ]
    ))

    # 2. Statistical analysis section
    if "report_stats" in tool_results and tool_results["report_stats"].ok:
        res = tool_results["report_stats"]
        findings = []
        for col, stats in list(res.data.items())[:4]:
            if isinstance(stats, dict) and "mean" in stats:
                findings.append(Finding(
                    statement=(
                        f"For '{col}', values range from {stats.get('min', 0):.2f} to {stats.get('max', 0):.2f}, "
                        f"with an average of {stats.get('mean', 0):.2f} and a typical middle value (median) of {stats.get('median', 0):.2f}."
                    ),
                    evidence="statistical_analysis (report_stats)"
                ))
        sections.append(ReportSection(
            heading="2. Key Numbers & Typical Ranges",
            body_markdown="Here is what the main numerical measurements look like on average and how spread out they are.",
            findings=findings,
            chart_specs=[
                adapt_chart_for_dataset(sc, ctx, tool_results)
                for sc in res.suggested_charts[:2]
            ]
        ))

    # 3. Category Comparisons
    if "report_agg_0" in tool_results and tool_results["report_agg_0"].ok:
        agg_res = tool_results["report_agg_0"]
        sections.append(ReportSection(
            heading="3. Comparisons Across Categories",
            body_markdown="Comparing how key measurements differ from one category or group to another.",
            findings=[
                Finding(
                    statement=agg_res.summary,
                    evidence="aggregate_data (report_agg_0)"
                )
            ],
            chart_specs=[
                adapt_chart_for_dataset(sc, ctx, tool_results)
                for sc in agg_res.suggested_charts[:1]
            ]
        ))

    # 4. Correlation section
    if "report_corr" in tool_results and tool_results["report_corr"].ok:
        c_res = tool_results["report_corr"]
        findings = []
        for pair in (c_res.table or [])[:3]:
            findings.append(Finding(
                statement=f"'{pair.get('feature1')}' and '{pair.get('feature2')}' have a {pair.get('strength')} link (correlation: {pair.get('correlation')}).",
                evidence="correlation_analysis (report_corr)",
                confidence_note="Note: A correlation shows that two numbers move together, not that one causes the other."
            ))
        sections.append(ReportSection(
            heading="4. How Different Factors Relate to Each Other",
            body_markdown="We checked whether increases in one measurement tend to go hand-in-hand with increases or decreases in another.",
            findings=findings,
            chart_specs=[
                adapt_chart_for_dataset(sc, ctx, tool_results)
                for sc in c_res.suggested_charts[:1]
            ]
        ))

    # 5. Outliers section
    if "report_outliers" in tool_results and tool_results["report_outliers"].ok:
        o_res = tool_results["report_outliers"]
        findings = []
        has_any_outliers = False
        for col, info in list(o_res.data.items())[:3]:
            cnt = info.get("outlier_count", 0)
            if cnt > 0:
                has_any_outliers = True
            findings.append(Finding(
                statement=f"'{col}' has {cnt} unusually high or low entries ({info.get('outlier_pct', 0)}% of records).",
                evidence="outlier_detection (report_outliers)",
                confidence_note="Unusual values are potential outliers—they may represent standout real-world cases rather than data mistakes."
            ))
        outlier_charts = (
            [adapt_chart_for_dataset(sc, ctx, tool_results) for sc in o_res.suggested_charts[:1]]
            if (has_any_outliers and ctx.n_rows >= 30)
            else []
        )
        sections.append(ReportSection(
            heading="5. Unusual or Standout Records (Outliers)",
            body_markdown="Screening for extreme values that sit far outside the typical range.",
            findings=findings,
            chart_specs=outlier_charts
        ))

    return ReportDraft(
        title=f"Data Analysis Report: {ctx.name}",
        plain_english_guide=plain_guide,
        executive_summary=(
            f"This report summarizes what the '{ctx.name}' dataset ({ctx.n_rows:,} records, {ctx.n_cols} columns) is about, "
            "what its main numbers and categories tell us in plain language, and where the notable patterns and standout values lie."
        ),
        sections=sections,
        recommendations=[
            "Review any columns with missing entries before relying on them for critical business decisions.",
            "Inspect the standout (outlier) records highlighted above to understand what makes those cases unique.",
            "Focus on the strongest category differences and relationships identified in this report for deeper follow-up."
        ],
        limitations=[
            "Patterns and correlations observed in the data show associations, not direct cause-and-effect.",
            "Automated category and type detection is based on the uploaded snapshot of data."
        ],
        not_performed=not_performed
    )


def generate_report_draft(
    ctx: DatasetContext,
    llm_client: LLMClient,
    user_question: Optional[str] = None,
    session_tools: Optional[Dict[str, ToolResult]] = None,
    memory_service: Optional[MemoryService] = None,
) -> tuple[ReportDraft, Dict[str, ToolResult]]:
    """Runs evidence gathering and asks LLM (or falls back) to produce ReportDraft."""
    mem_svc = memory_service or get_memory_service()
    evidence, tool_results, not_performed = build_report_evidence(
        ctx, session_tools=session_tools, memory_service=mem_svc, user_question=user_question
    )
    _, memory_prompt_block, _ = mem_svc.retrieve_for_task(
        query=user_question or "comprehensive report summary",
        ctx=ctx,
        task_type="report",
        wants_chart=True,
    )

    requested_types = detect_requested_chart_types(user_question or "")
    chart_profile = analyze_dataset_chart_profile(ctx)
    curated_specs = curate_report_charts(ctx, tool_results, requested_types=requested_types)
    all_suggested_charts = [sc.model_dump() for sc in curated_specs]

    payload = {
        "evidence": evidence,
        "dataset_chart_profile": {
            "size_tier": chart_profile["size_tier"],
            "n_rows": chart_profile["n_rows"],
            "recommended_chart_types": requested_types or chart_profile["recommended_chart_types"],
            "allow_box_plots": chart_profile["allow_box"],
        },
        "not_performed_notes": not_performed,
        "available_charts": all_suggested_charts[:8],
        "user_question": user_question or "Comprehensive general exploratory data analysis explained clearly for a non-technical reader."
    }

    sys_prompt = REPORT_SYSTEM_PROMPT
    if memory_prompt_block:
        sys_prompt = f"{REPORT_SYSTEM_PROMPT}\n\n{memory_prompt_block}"

    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": f"Generate the report draft in structured JSON conforming to the ReportDraft schema for this evidence:\n{json.dumps(payload, default=str)}"}
    ]

    try:
        report_json = llm_client.generate_json(messages)
        draft = ReportDraft(**report_json)

        if not draft.plain_english_guide or not draft.plain_english_guide.strip():
            draft.plain_english_guide = _build_default_plain_english_guide(ctx, tool_results)

        # Validate and adapt chart specs inside draft so inappropriate chart types (e.g. box on small datasets) never appear
        for sec in draft.sections:
            valid_charts = []
            for spec in sec.chart_specs:
                spec = adapt_chart_for_dataset(spec, ctx, tool_results, explicitly_requested_types=requested_types)
                if requested_types and spec.chart_type not in requested_types:
                    continue
                if spec.source == "tool_result" and not spec.tool_result_id:
                    for cand in all_suggested_charts:
                        if cand.get("chart_type") == spec.chart_type and cand.get("x") == spec.x:
                            spec.tool_result_id = cand.get("tool_result_id")
                            break
                ok, errs, v_spec = validate_chart_spec(spec, ctx, tool_results)
                if ok:
                    valid_charts.append(v_spec)
            sec.chart_specs = valid_charts

        return draft, tool_results
    except Exception:
        fallback = build_template_fallback_report(ctx, evidence, not_performed, tool_results)
        return fallback, tool_results
