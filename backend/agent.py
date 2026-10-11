import json
import re
import time
from typing import List, Dict, Any, Tuple, Optional
from backend.dataset import DatasetContext
from backend.tools import get_tool_schemas, get_tool, TOOL_REGISTRY
from backend.schemas import AgentResponse, Block, ToolCallRecord, ChartSpec, ToolResult
from backend.llm_client import LLMClient
from backend.viz.spec import (
    validate_chart_spec,
    detect_requested_chart_types,
    analyze_dataset_chart_profile,
    adapt_chart_for_dataset,
    build_requested_chart_spec,
)
from backend.memory import MemoryService, get_memory_service
from pydantic import ValidationError

CHART_KEYWORDS = re.compile(
    r"\b(chart|charts|graph|graphs|plot|plots|plotting|visual|visualize|visualization|visualisation|"
    r"histogram|histograms|scatter|scatterplot|boxplot|box\s*plot|heatmap|heat\s*map|"
    r"bar\s*chart|bar\s*graph|bar\s*plot|barchart|barplot|column\s*chart|"
    r"line\s*chart|line\s*graph|line\s*plot|linechart|lineplot|trend\s*line|"
    r"pie\s*chart|pie\s*graph|donut\s*chart|doughnut\s*chart|diagram|figure|draw)\b",
    re.IGNORECASE,
)

SYSTEM_PROMPT = """You are a warm, articulate, and insightful AI Data Analyst helping a user understand their uploaded dataset.
You are given a compact schema summary of the dataset (not the raw rows) and a suite of deterministic analysis tools.

CORE PRINCIPLES
1. Always use the provided tools to compute statistics, aggregations, filters, correlations, outliers, or time trends. Never guess, estimate, or make up numbers. Every metric in your response must come from a tool result.
2. Communicate in natural, engaging, human-friendly English—like a helpful senior analyst explaining insights to a colleague. Avoid robotic data dumps or raw variable names without context.
3. Structure your answers for readability:
   - Start with a **clear, friendly headline takeaway** that directly answers the user's question.
   - Organize details under clean `###` section headings.
   - Use bullet points with **bold key terms** and explain what the numbers mean in plain, everyday language.
   - Include compact Markdown tables when comparing multiple items or categories.
   - End with an **interactive follow-up prompt** (e.g., suggesting 1-2 interesting next questions or asking if they'd like you to plot a chart for a specific metric).
4. Use only column names that exist in the schema. If a user's request is ambiguous, ask a polite clarifying question listing the closest matching columns.
5. Never claim causation from correlation. Describe statistical extremes as "potential outliers" rather than errors.
6. Never answer any question that is unrelated to the dataset (unless the user is explicitly asking you to remember or forget an analytical preference or domain definition).
7. When PERSISTENT USER MEMORY & DOMAIN RULES are provided below, actively apply them when choosing tool filters, aggregations, metrics, and response formatting. If a stored memory conflicts with the user's explicit current instruction or the current dataset's actual columns, prioritize the current instruction/dataset and politely note the difference.

TOOL USAGE RULES
- `aggregate_data`: pass `group_by` (list of column names) and `aggregations` (list of objects with `column` and `function`). Example: `{"group_by": ["Category"], "aggregations": [{"column": "Sales", "function": "sum"}]}`
- `filter_data`: pass `conditions` (list of objects with `column`, `operator`, `value`).
- `statistical_analysis`: pass `columns` (list of column names).
- `correlation_analysis`: pass `columns` (list of column names).
- `outlier_detection`: pass `columns` (list of column names).
- `time_series_analysis`: pass `value_columns` (list of numeric column names) and optional `date_column`.

STRICT CHART POLICY
- **DO NOT include or propose any charts or graphs unless the user EXPLICITLY asks for a chart, graph, plot, or visualization** in their message.
- For general questions, dataset summaries, statistical questions, or comparisons where no visual was requested, return ONLY well-formatted `markdown` blocks (and `table` blocks if useful).
- When the user DOES explicitly ask for a chart/graph:
  * If the user asked for a **specific chart type** (e.g., `bar`, `line`, `scatter`, `histogram`, `box`, `heatmap`, `pie`), return **ONLY** that exact chart type and no other chart types.
  * If the user asked for a general chart/graph without naming a specific type, select the most suitable chart type for the dataset's size and column structure (`bar` for category comparisons or small datasets `< 30` rows, `line` for date/time trends, `scatter` for two numeric columns, `histogram` for continuous distributions on medium/large datasets, and avoid `box` plots on small datasets).

OUTPUT FORMAT
Return your final answer in structured JSON matching this schema:
{
  "blocks": [
    {
      "type": "markdown",
      "text": "**Headline takeaway in plain English**\\n\\n### Key Insights\\n- **Metric**: Explanation...\\n\\n*Would you like to explore X or see a bar chart of Y?*"
    }
  ]
}
(Only include `{"type": "chart", "chart": { ...ChartSpec... }}` inside `blocks` when the user explicitly requested a chart/graph.)"""


def user_requested_chart(user_question: str) -> bool:
    """Returns True only if the user's message explicitly asks for a chart, graph, or plot."""
    if not user_question:
        return False
    return bool(CHART_KEYWORDS.search(user_question))


class DataAgent:
    def __init__(self, llm_client: LLMClient, memory_service: Optional[MemoryService] = None):
        self.llm = llm_client
        self.memory_service = memory_service or get_memory_service()
        self.max_steps = 6

    def _create_system_message(
        self,
        ctx: DatasetContext,
        wants_chart: bool,
        memory_prompt_block: str = "",
        requested_chart_types: Optional[List[str]] = None,
        chart_profile: Optional[Dict[str, Any]] = None,
    ) -> dict:
        schema_summary = ctx.to_llm_schema_summary()
        requested_chart_types = requested_chart_types or []
        chart_profile = chart_profile or analyze_dataset_chart_profile(ctx)

        if wants_chart:
            if requested_chart_types:
                chart_directive = (
                    f"\n\nUSER CHART PREFERENCE FOR THIS TURN: The user EXPLICITLY requested ONLY the following specific chart type(s): "
                    f"{requested_chart_types}. You MUST include ONLY `chart` block(s) with `chart_type` in {requested_chart_types} "
                    f"and NO other chart types."
                )
            else:
                box_note = (
                    "Do NOT use `box` plots because this dataset is small (< 30 rows); use `bar`, `line`, or `scatter` instead."
                    if not chart_profile["allow_box"]
                    else "Only use `box` plots if specifically highlighting outlier spread."
                )
                chart_directive = (
                    f"\n\nUSER CHART PREFERENCE FOR THIS TURN: The user EXPLICITLY asked for a chart/graph without naming a single type. "
                    f"Dataset size tier: '{chart_profile['size_tier']}' ({chart_profile['n_rows']} rows). "
                    f"Recommended chart types for this dataset: {chart_profile['recommended_chart_types']}. {box_note} "
                    f"Include 1-2 appropriate `chart` blocks alongside your conversational markdown explanation."
                )
        else:
            chart_directive = (
                "\n\nUSER CHART PREFERENCE FOR THIS TURN: The user did NOT ask for a chart or graph. "
                "Do NOT include any `chart` blocks. Provide a rich, well-formatted, interactive natural-English markdown response only."
            )

        memory_section = f"\n\n{memory_prompt_block}" if memory_prompt_block else ""
        return {
            "role": "system",
            "content": f"{SYSTEM_PROMPT}{chart_directive}{memory_section}\n\nDATASET SCHEMA:\n{json.dumps(schema_summary, indent=2)}",
        }

    def run(
        self,
        user_question: str,
        ctx: DatasetContext,
        history: List[Dict[str, Any]],
    ) -> Tuple[AgentResponse, Dict[str, Any]]:
        wants_chart = user_requested_chart(user_question)
        requested_chart_types = detect_requested_chart_types(user_question) if wants_chart else []
        chart_profile = analyze_dataset_chart_profile(ctx)
        warnings: List[str] = []

        # 1. Process incoming user message for persistent memory updates (Save / Update / Forget)
        memory_action_note = None
        try:
            cand, mem_record = self.memory_service.process_user_turn(
                user_message=user_question,
                ctx=ctx,
                llm_client=self.llm,
            )
            if cand.action == "save" and mem_record:
                memory_action_note = f"Saved to persistent memory ({mem_record.memory_type}): {mem_record.content}"
            elif cand.action == "update" and mem_record:
                memory_action_note = f"Updated persistent memory ({mem_record.memory_type}): {mem_record.content}"
            elif cand.action == "delete":
                memory_action_note = f"Removed from persistent memory: {cand.content or 'matching rule'}"
        except Exception:
            pass

        # 2. Retrieve relevant persistent memories for the current question and dataset
        memory_prompt_block = ""
        tool_hints: Dict[str, Any] = {}
        try:
            _, memory_prompt_block, tool_hints = self.memory_service.retrieve_for_task(
                query=user_question,
                ctx=ctx,
                task_type="chart" if wants_chart else "chat",
                wants_chart=wants_chart,
            )
        except Exception:
            warnings.append("Persistent memory retrieval is temporarily unavailable; continuing with standard session context.")

        if memory_action_note:
            warnings.append(memory_action_note)

        messages = [
            self._create_system_message(
                ctx,
                wants_chart,
                memory_prompt_block,
                requested_chart_types=requested_chart_types,
                chart_profile=chart_profile,
            )
        ] + history[-10:]
        messages.append({"role": "user", "content": user_question})

        tools = get_tool_schemas()
        tool_trace = []

        new_tool_results = {}  # id -> ToolResult for UI to keep

        step = 0
        while step < self.max_steps:
            step += 1

            # call LLM
            response = self.llm.chat(messages, tools=tools)
            messages.append(response)

            if not response.get("tool_calls"):
                break  # LLM is done calling tools

            # execute tools
            broke_for_final_json = False
            for tc in response["tool_calls"]:
                t_name = tc["function"]["name"]
                t_args_str = tc["function"]["arguments"]
                t_id = tc["id"]

                start_time = time.time()

                try:
                    t_args = json.loads(t_args_str) if isinstance(t_args_str, str) else t_args_str
                except Exception:
                    t_args = {}

                # If the model called "json" or "response" to return its final structured answer
                if t_name.lower() in ["json", "agentresponse", "response", "final_response"]:
                    if not response.get("content"):
                        response["content"] = t_args_str if isinstance(t_args_str, str) else json.dumps(t_args)
                    broke_for_final_json = True
                    break

                # Apply retrieved memory tool hints where appropriate and not explicitly overridden
                if isinstance(t_args, dict) and tool_hints:
                    if t_name == "time_series_analysis" and not t_args.get("frequency") and tool_hints.get("preferred_time_freq"):
                        t_args["frequency"] = tool_hints["preferred_time_freq"]

                tool_instance = get_tool(t_name)
                if not tool_instance:
                    res = ToolResult(
                        tool=t_name,
                        ok=False,
                        summary=f"Tool '{t_name}' not found. Available tools: {list(TOOL_REGISTRY.keys())}",
                        data={},
                        error=f"Tool '{t_name}' is not in the tool registry.",
                    )
                else:
                    try:
                        res = tool_instance.run(ctx, **t_args)
                    except ValidationError as ve:
                        res = ToolResult(tool=t_name, ok=False, summary="Validation Error", data={}, error=str(ve))
                    except Exception as e:
                        res = ToolResult(tool=t_name, ok=False, summary="Execution Error", data={}, error=str(e))

                duration_ms = int((time.time() - start_time) * 1000)

                tool_trace.append(
                    ToolCallRecord(
                        name=t_name,
                        args=t_args if "t_args" in locals() else {},
                        ok=res.ok,
                        summary=res.summary,
                        duration_ms=duration_ms,
                    )
                )

                new_tool_results[t_id] = res

                # build digest for LLM (only expose suggested_charts if user asked for a chart)
                suggested = []
                if wants_chart and res.suggested_charts:
                    for sc in res.suggested_charts:
                        sc_adapted = adapt_chart_for_dataset(
                            sc, ctx, new_tool_results, explicitly_requested_types=requested_chart_types
                        )
                        if requested_chart_types and sc_adapted.chart_type not in requested_chart_types:
                            continue
                        sc_dump = sc_adapted.model_dump()
                        if sc_adapted.source == "tool_result":
                            sc_dump["tool_result_id"] = t_id
                        suggested.append(sc_dump)

                if wants_chart and requested_chart_types and not suggested:
                    for r_type in requested_chart_types:
                        built_spec = build_requested_chart_spec(r_type, ctx, new_tool_results, user_question)
                        if built_spec:
                            suggested.append(built_spec.model_dump())

                digest = {
                    "tool": t_name,
                    "ok": res.ok,
                    "summary": res.summary,
                    "data": res.data,
                    "table_preview": (res.table[:10] if res.table else None),
                    "error": res.error,
                }
                if wants_chart:
                    digest["suggested_charts"] = suggested

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": t_id,
                        "content": json.dumps(digest, default=str),
                    }
                )

            if broke_for_final_json:
                break

        # Final formatting step
        blocks = []
        final_content = (response.get("content") or "").strip()

        parsed_blocks = None
        extracted_text = None
        if final_content:
            try:
                candidate = final_content
                if "```json" in candidate:
                    candidate = candidate.split("```json")[1].split("```")[0].strip()
                elif "```" in candidate and candidate.startswith("```"):
                    candidate = candidate.split("```")[1].split("```")[0].strip()

                if candidate.startswith("{"):
                    data = json.loads(candidate)
                    if isinstance(data, dict):
                        if "blocks" in data and isinstance(data["blocks"], list):
                            parsed_blocks = data["blocks"]
                        elif "text" in data and isinstance(data["text"], str):
                            extracted_text = data["text"]
                        elif "answer" in data and isinstance(data["answer"], str):
                            extracted_text = data["answer"]
                        elif "summary" in data and isinstance(data["summary"], str):
                            extracted_text = data["summary"]
            except Exception:
                pass

        if parsed_blocks:
            for b in parsed_blocks:
                try:
                    block = Block(**b)
                    if block.type == "chart":
                        # Strictly enforce: only render charts if user explicitly asked for one
                        if not wants_chart or not block.chart:
                            continue
                        # Adapt chart to dataset size/structure unless user explicitly requested that type
                        block.chart = adapt_chart_for_dataset(
                            block.chart,
                            ctx,
                            new_tool_results,
                            explicitly_requested_types=requested_chart_types,
                        )
                        # Strictly enforce: if user asked for a specific chart type, drop any other chart type
                        if requested_chart_types and block.chart.chart_type not in requested_chart_types:
                            continue
                        # Auto-resolve missing tool_result_id if needed
                        if (
                            block.chart.source == "tool_result"
                            and not block.chart.tool_result_id
                            and new_tool_results
                        ):
                            block.chart.tool_result_id = list(new_tool_results.keys())[-1]
                        ok, errs, v_spec = validate_chart_spec(block.chart, ctx, new_tool_results)
                        if ok:
                            block.chart = v_spec
                            blocks.append(block)
                        else:
                            warnings.extend(errs)
                    else:
                        blocks.append(block)
                except Exception:
                    pass
        else:
            text_to_show = extracted_text or final_content
            if text_to_show:
                blocks.append(Block(type="markdown", text=text_to_show))
            else:
                blocks.append(Block(type="markdown", text="Here are the results from the analysis."))

        # If the user explicitly asked for a specific chart type, guarantee that exact chart type is shown
        if wants_chart and requested_chart_types:
            existing_chart_types = {b.chart.chart_type for b in blocks if b.type == "chart" and b.chart}
            for r_type in requested_chart_types:
                if r_type not in existing_chart_types:
                    built_spec = build_requested_chart_spec(r_type, ctx, new_tool_results, user_question)
                    if built_spec:
                        blocks.append(Block(type="chart", chart=built_spec))

        # If the user asked for a generic chart/graph without naming a specific type and none was emitted yet,
        # select the best dataset-appropriate chart
        elif wants_chart and not any(b.type == "chart" for b in blocks):
            pref_type = tool_hints.get("preferred_chart_type")
            if pref_type == "box" and not chart_profile["allow_box"]:
                pref_type = None

            if pref_type:
                built_pref = build_requested_chart_spec(pref_type, ctx, new_tool_results, user_question)
                if built_pref:
                    blocks.append(Block(type="chart", chart=built_pref))

            if not any(b.type == "chart" for b in blocks):
                for t_id, tr in new_tool_results.items():
                    if tr.ok and tr.suggested_charts:
                        for sc in tr.suggested_charts[:1]:
                            sc_copy = sc.model_copy(deep=True)
                            if sc_copy.source == "tool_result":
                                sc_copy.tool_result_id = t_id
                            sc_adapted = adapt_chart_for_dataset(sc_copy, ctx, new_tool_results)
                            ok, errs, v_spec = validate_chart_spec(sc_adapted, ctx, new_tool_results)
                            if ok:
                                blocks.append(Block(type="chart", chart=v_spec))
                                break
                    if any(b.type == "chart" for b in blocks):
                        break

            if not any(b.type == "chart" for b in blocks) and chart_profile["recommended_chart_types"]:
                best_type = chart_profile["recommended_chart_types"][0]
                built_default = build_requested_chart_spec(best_type, ctx, new_tool_results, user_question)
                if built_default:
                    blocks.append(Block(type="chart", chart=built_default))

        return (
            AgentResponse(
                blocks=blocks,
                tool_trace=tool_trace,
                warnings=warnings,
            ),
            new_tool_results,
        )
