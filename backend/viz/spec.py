import re
from typing import Tuple, Dict, Any, List, Optional
from backend.schemas import ChartSpec, ToolResult
from backend.dataset import DatasetContext

VALID_CHART_TYPES = ["bar", "line", "histogram", "scatter", "box", "heatmap"]

# Explicit chart type detection patterns (ordered from most specific to general)
SPECIFIC_CHART_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("box", re.compile(r"\b(box\s*plot|boxplot|box\s*chart|box\s*and\s*whisker|whisker\s*plot)s?\b", re.IGNORECASE)),
    ("histogram", re.compile(r"\b(histogram|histograms|distribution\s+histogram)\b", re.IGNORECASE)),
    ("heatmap", re.compile(r"\b(heatmap|heat\s*map|correlation\s+matrix|correlation\s+heatmap)s?\b", re.IGNORECASE)),
    ("scatter", re.compile(r"\b(scatter\s*plot|scatter\s*chart|scatter\s*graph|scatterplot|scatter)s?\b", re.IGNORECASE)),
    ("line", re.compile(r"\b(line\s*chart|line\s*graph|line\s*plot|lineplot|linechart|trend\s*line|trend\s*chart)s?\b", re.IGNORECASE)),
    ("bar", re.compile(r"\b(bar\s*chart|bar\s*graph|bar\s*plot|barplot|barchart|column\s*chart|bar\s+comparison)s?\b", re.IGNORECASE)),
]


def detect_requested_chart_types(user_question: str) -> List[str]:
    """Detects if the user explicitly asked for one or more specific chart types (e.g., 'bar chart', 'scatter plot').
    Returns an ordered list of canonical chart_type strings (e.g., ['bar'], ['scatter']).
    Returns [] if the user only asked for a generic 'chart', 'graph', or 'plot' without naming a type."""
    if not user_question:
        return []
    matched: List[Tuple[int, str]] = []
    for c_type, pattern in SPECIFIC_CHART_PATTERNS:
        m = pattern.search(user_question)
        if m:
            matched.append((m.start(), c_type))
    matched.sort(key=lambda x: x[0])
    seen = []
    for _, c_type in matched:
        if c_type not in seen:
            seen.append(c_type)
    return seen


def analyze_dataset_chart_profile(ctx: DatasetContext) -> Dict[str, Any]:
    """Analyzes the dataset's row count, column types, and cardinality to determine
    which chart types are statistically meaningful and visually effective."""
    n_rows = ctx.n_rows
    num_cols = [c for c, info in ctx.schema.items() if info.semantic_type == "numeric"]
    cat_cols = [c for c, info in ctx.schema.items() if info.semantic_type == "categorical"]
    date_cols = [c for c, info in ctx.schema.items() if info.semantic_type == "datetime"]
    id_cols = [c for c, info in ctx.schema.items() if info.semantic_type in ("id_like", "text")]

    # Determine best label/category column for x-axis comparisons
    primary_cat_col: Optional[str] = None
    for c in cat_cols:
        if 2 <= ctx.schema[c].nunique <= 20:
            primary_cat_col = c
            break
    if not primary_cat_col and cat_cols:
        primary_cat_col = cat_cols[0]

    primary_label_col: Optional[str] = primary_cat_col or (id_cols[0] if id_cols else None)

    # Box plots require a sufficient sample size (>= 30 rows) and non-trivial cardinality
    # to make quartiles/whiskers visually meaningful.
    allow_box = n_rows >= 30 and any(ctx.schema[c].nunique >= 10 for c in num_cols)
    # Histograms require at least 15 rows and continuous variation; for tiny datasets, bar charts are much clearer.
    allow_histogram = n_rows >= 15 and any(ctx.schema[c].nunique >= 8 for c in num_cols)

    if n_rows < 30:
        size_tier = "small"
    elif n_rows < 150:
        size_tier = "medium"
    else:
        size_tier = "large"

    recommended: List[str] = []
    if cat_cols and num_cols:
        recommended.append("bar")
    if date_cols and num_cols:
        recommended.append("line")
    if len(num_cols) >= 2:
        recommended.append("scatter")
    if allow_histogram and num_cols:
        recommended.append("histogram")
    if len(num_cols) >= 3 and n_rows >= 10:
        recommended.append("heatmap")
    if not recommended and num_cols:
        recommended.append("bar")
    if allow_box and n_rows >= 50:
        recommended.append("box")

    return {
        "size_tier": size_tier,
        "n_rows": n_rows,
        "num_cols": num_cols,
        "cat_cols": cat_cols,
        "date_cols": date_cols,
        "primary_cat_col": primary_cat_col,
        "primary_label_col": primary_label_col,
        "allow_box": allow_box,
        "allow_histogram": allow_histogram,
        "recommended_chart_types": recommended,
    }


def adapt_chart_for_dataset(
    spec: ChartSpec,
    ctx: DatasetContext,
    tool_results: Optional[Dict[str, ToolResult]] = None,
    explicitly_requested_types: Optional[List[str]] = None,
) -> ChartSpec:
    """Replaces inefficient chart choices (such as box plots or histograms on small datasets)
    with dataset-appropriate chart specs unless the user explicitly requested that chart type."""
    explicitly_requested_types = explicitly_requested_types or []
    profile = analyze_dataset_chart_profile(ctx)
    adapted = spec.model_copy(deep=True)

    # Never override if user explicitly requested this exact chart type
    if adapted.chart_type in explicitly_requested_types:
        return adapted

    # 1. Replace box plots when dataset is small (< 30 rows) or box plots are not appropriate
    if adapted.chart_type == "box" and not profile["allow_box"]:
        metric_col = adapted.y if isinstance(adapted.y, str) else (profile["num_cols"][0] if profile["num_cols"] else None)
        x_col = adapted.x or profile["primary_label_col"]
        if x_col and metric_col and x_col != metric_col:
            adapted.chart_type = "bar"
            adapted.source = "dataset"
            adapted.tool_result_id = None
            adapted.x = x_col
            adapted.y = metric_col
            adapted.title = f"{metric_col} by {x_col}"
        elif profile["allow_histogram"] and metric_col:
            adapted.chart_type = "histogram"
            adapted.source = "dataset"
            adapted.tool_result_id = None
            adapted.x = metric_col
            adapted.y = None
            adapted.title = f"Distribution of {metric_col}"
        elif len(profile["num_cols"]) >= 2:
            c1, c2 = profile["num_cols"][0], profile["num_cols"][1]
            adapted.chart_type = "scatter"
            adapted.source = "dataset"
            adapted.tool_result_id = None
            adapted.x = c1
            adapted.y = c2
            adapted.title = f"{c1} vs {c2}"
        elif metric_col:
            adapted.chart_type = "bar"
            adapted.source = "dataset"
            adapted.tool_result_id = None
            adapted.x = x_col
            adapted.y = metric_col
            adapted.title = f"Comparison of {metric_col}"

    # 2. Replace histograms on very small datasets (< 15 rows) with bar charts
    elif adapted.chart_type == "histogram" and not profile["allow_histogram"]:
        metric_col = adapted.x or (profile["num_cols"][0] if profile["num_cols"] else None)
        x_col = profile["primary_label_col"]
        if metric_col:
            adapted.chart_type = "bar"
            adapted.source = "dataset"
            adapted.tool_result_id = None
            adapted.x = x_col if x_col and x_col != metric_col else None
            adapted.y = metric_col
            adapted.title = f"{metric_col} by {x_col}" if (x_col and x_col != metric_col) else f"Values of {metric_col}"

    return adapted


def _extract_mentioned_columns(user_question: str, ctx: DatasetContext) -> List[str]:
    """Finds dataset columns mentioned in the user's question (longest match first)."""
    if not user_question:
        return []
    q_lower = user_question.lower()
    matches: List[Tuple[int, str]] = []
    for col in sorted(ctx.schema.keys(), key=len, reverse=True):
        col_low = col.lower()
        col_spaced = col_low.replace("_", " ")
        idx = q_lower.find(col_low)
        if idx == -1 and col_spaced != col_low:
            idx = q_lower.find(col_spaced)
        if idx != -1:
            matches.append((idx, col))
    matches.sort(key=lambda x: x[0])
    seen = []
    for _, col in matches:
        if col not in seen:
            seen.append(col)
    return seen


def build_requested_chart_spec(
    requested_type: str,
    ctx: DatasetContext,
    tool_results: Optional[Dict[str, ToolResult]] = None,
    user_question: str = "",
) -> Optional[ChartSpec]:
    """Deterministically constructs a valid ChartSpec matching `requested_type` using
    columns mentioned in `user_question`, executed tool results, or the dataset schema."""
    tool_results = tool_results or {}
    profile = analyze_dataset_chart_profile(ctx)
    mentioned = _extract_mentioned_columns(user_question, ctx)
    mentioned_num = [c for c in mentioned if ctx.schema[c].semantic_type == "numeric"]
    mentioned_cat = [c for c in mentioned if ctx.schema[c].semantic_type in ("categorical", "id_like", "text", "boolean")]
    mentioned_date = [c for c in mentioned if ctx.schema[c].semantic_type == "datetime"]

    num_cols = mentioned_num + [c for c in profile["num_cols"] if c not in mentioned_num]
    cat_cols = mentioned_cat + [c for c in profile["cat_cols"] if c not in mentioned_cat]
    date_cols = mentioned_date + [c for c in profile["date_cols"] if c not in mentioned_date]

    # First check if any executed tool already produced a suggested chart of this exact type
    for t_id, tr in tool_results.items():
        if tr.ok and tr.suggested_charts:
            for sc in tr.suggested_charts:
                if sc.chart_type == requested_type:
                    sc_copy = sc.model_copy(deep=True)
                    if sc_copy.source == "tool_result":
                        sc_copy.tool_result_id = t_id
                    ok, _, v_spec = validate_chart_spec(sc_copy, ctx, tool_results)
                    if ok:
                        return v_spec

    # Otherwise construct from dataset schema
    if requested_type == "bar":
        x_col = cat_cols[0] if cat_cols else (date_cols[0] if date_cols else profile["primary_label_col"])
        y_col = num_cols[0] if num_cols else None
        if x_col and y_col and x_col != y_col:
            spec = ChartSpec(chart_type="bar", title=f"{y_col} by {x_col}", source="dataset", x=x_col, y=y_col)
        elif x_col:
            spec = ChartSpec(chart_type="bar", title=f"Count by {x_col}", source="dataset", x=x_col, y=None)
        elif y_col:
            spec = ChartSpec(chart_type="bar", title=f"Comparison of {y_col}", source="dataset", x=None, y=y_col)
        else:
            return None

    elif requested_type == "pie":
        x_col = cat_cols[0] if cat_cols else profile["primary_label_col"]
        y_col = num_cols[0] if num_cols else None
        if not x_col:
            return None
        title = f"Share of {y_col} by {x_col}" if y_col else f"Proportion by {x_col}"
        spec = ChartSpec(chart_type="pie", title=title, source="dataset", x=x_col, y=y_col)

    elif requested_type == "line":
        x_col = date_cols[0] if date_cols else (cat_cols[0] if cat_cols else (num_cols[1] if len(num_cols) >= 2 else None))
        y_col = num_cols[0] if num_cols else None
        if not y_col:
            return None
        spec = ChartSpec(
            chart_type="line",
            title=f"{y_col} Trend over {x_col}" if x_col else f"{y_col} Trend",
            source="dataset",
            x=x_col,
            y=y_col,
        )

    elif requested_type == "scatter":
        if len(num_cols) >= 2:
            x_col, y_col = num_cols[0], num_cols[1]
            color_col = cat_cols[0] if cat_cols and ctx.schema[cat_cols[0]].nunique <= 12 else None
            spec = ChartSpec(
                chart_type="scatter",
                title=f"{y_col} vs {x_col}",
                source="dataset",
                x=x_col,
                y=y_col,
                color=color_col,
            )
        elif len(num_cols) == 1:
            y_col = num_cols[0]
            x_col = cat_cols[0] if cat_cols else (date_cols[0] if date_cols else None)
            spec = ChartSpec(chart_type="scatter", title=f"{y_col} Scatter Plot", source="dataset", x=x_col, y=y_col)
        else:
            return None

    elif requested_type == "histogram":
        x_col = num_cols[0] if num_cols else (date_cols[0] if date_cols else None)
        if not x_col:
            return None
        spec = ChartSpec(
            chart_type="histogram",
            title=f"Distribution of {x_col}",
            source="dataset",
            x=x_col,
            bins=min(20, max(5, ctx.n_rows // 2)),
        )

    elif requested_type == "box":
        y_col = num_cols[0] if num_cols else None
        if not y_col:
            return None
        x_col = cat_cols[0] if (cat_cols and ctx.schema[cat_cols[0]].nunique <= 15) else None
        spec = ChartSpec(
            chart_type="box",
            title=f"Box Plot of {y_col}" + (f" by {x_col}" if x_col else ""),
            source="dataset",
            x=x_col,
            y=y_col,
        )

    elif requested_type == "heatmap":
        # Check if any tool result has a correlation matrix
        for t_id, tr in tool_results.items():
            if tr.ok and tr.chart_data and "matrix" in tr.chart_data:
                return ChartSpec(
                    chart_type="heatmap",
                    title="Correlation Heatmap",
                    source="tool_result",
                    tool_result_id=t_id,
                )
        spec = ChartSpec(
            chart_type="heatmap",
            title="Correlation Matrix Heatmap",
            source="dataset",
        )
    else:
        return None

    ok, _, v_spec = validate_chart_spec(spec, ctx, tool_results)
    return v_spec if ok else None


def curate_report_charts(
    ctx: DatasetContext,
    tool_results: Dict[str, ToolResult],
    requested_types: Optional[List[str]] = None,
) -> List[ChartSpec]:
    """Selects a diverse, dataset-appropriate set of charts for the report.
    - If `requested_types` is non-empty, returns ONLY charts of those types.
    - For small datasets (< 30 rows), never includes box plots (uses bar, line, scatter instead).
    - Prioritizes visual variety across sections: category bar chart, time-series line chart,
      correlation scatter/heatmap, and distribution histogram."""
    requested_types = requested_types or []
    profile = analyze_dataset_chart_profile(ctx)

    if requested_types:
        curated: List[ChartSpec] = []
        for r_type in requested_types:
            built = build_requested_chart_spec(r_type, ctx, tool_results)
            if built:
                curated.append(built)
        return curated

    # Gather candidates by analytical category so report isn't flooded with one chart type
    agg_charts: List[ChartSpec] = []
    ts_charts: List[ChartSpec] = []
    corr_charts: List[ChartSpec] = []
    dist_charts: List[ChartSpec] = []
    outlier_charts: List[ChartSpec] = []

    for t_key, tr in tool_results.items():
        if not tr.ok or not tr.suggested_charts:
            continue
        for sc in tr.suggested_charts:
            sc_copy = sc.model_copy(deep=True)
            if sc_copy.source == "tool_result":
                sc_copy.tool_result_id = t_key
            sc_adapted = adapt_chart_for_dataset(sc_copy, ctx, tool_results, explicitly_requested_types=requested_types)
            ok, _, v_spec = validate_chart_spec(sc_adapted, ctx, tool_results)
            if not ok:
                continue

            if tr.tool == "aggregate_data":
                agg_charts.append(v_spec)
            elif tr.tool == "time_series_analysis":
                ts_charts.append(v_spec)
            elif tr.tool == "correlation_analysis":
                corr_charts.append(v_spec)
            elif tr.tool == "statistical_analysis":
                dist_charts.append(v_spec)
            elif tr.tool == "outlier_detection":
                # Only keep outlier box plots if dataset is medium/large and has actual outliers
                has_real_outliers = any(
                    isinstance(v, dict) and v.get("outlier_count", 0) > 0
                    for v in (tr.data or {}).values()
                )
                if profile["allow_box"] and has_real_outliers:
                    outlier_charts.append(v_spec)

    # Interleave best charts from each analytical dimension for maximum clarity
    ordered: List[ChartSpec] = []
    ordered.extend(agg_charts[:2])
    ordered.extend(ts_charts[:1])
    ordered.extend(corr_charts[:2])
    ordered.extend(dist_charts[:2])
    ordered.extend(outlier_charts[:1])

    # Deduplicate by (chart_type, x, y)
    unique_charts: List[ChartSpec] = []
    seen_keys = set()
    for ch in ordered:
        y_key = tuple(ch.y) if isinstance(ch.y, list) else ch.y
        key = (ch.chart_type, ch.x, y_key)
        if key not in seen_keys:
            seen_keys.add(key)
            unique_charts.append(ch)

    return unique_charts[:8]


def validate_chart_spec(
    spec: ChartSpec,
    ctx: DatasetContext,
    tool_results: Dict[str, ToolResult] = None,
) -> Tuple[bool, List[str], ChartSpec]:
    errors = []
    tool_results = tool_results or {}

    # Check chart type
    if spec.chart_type not in VALID_CHART_TYPES:
        return False, [f"Invalid chart_type '{spec.chart_type}'. Allowed: {VALID_CHART_TYPES}"], spec

    # Bounds checks
    if spec.bins and not (5 <= spec.bins <= 100):
        spec.bins = max(5, min(100, spec.bins))
    if spec.top_n and not (1 <= spec.top_n <= 50):
        spec.top_n = max(1, min(50, spec.top_n))

    cols_to_check = []
    if spec.x:
        cols_to_check.append(spec.x)
    if spec.y:
        if isinstance(spec.y, list):
            cols_to_check.extend(spec.y)
        else:
            cols_to_check.append(spec.y)
    if spec.color:
        cols_to_check.append(spec.color)

    # If source is tool_result, columns must be in tool result's chart_data
    if spec.source == "tool_result":
        if not spec.tool_result_id:
            errors.append("source is tool_result but tool_result_id is missing.")
        elif spec.tool_result_id not in tool_results:
            errors.append(f"Tool result '{spec.tool_result_id}' not found.")
        else:
            tr = tool_results[spec.tool_result_id]
            if not tr.chart_data:
                errors.append(f"Tool result '{spec.tool_result_id}' has no chart_data.")
            else:
                for c in cols_to_check:
                    if c not in tr.chart_data and c != "matrix":
                        errors.append(f"Column '{c}' not found in tool result chart_data.")
    else:
        # Check against dataset schema
        for c in cols_to_check:
            if c not in ctx.schema:
                lower_cols = {k.lower(): k for k in ctx.schema.keys()}
                if c.lower() in lower_cols:
                    if spec.x == c:
                        spec.x = lower_cols[c.lower()]
                    elif spec.color == c:
                        spec.color = lower_cols[c.lower()]
                    elif isinstance(spec.y, str) and spec.y == c:
                        spec.y = lower_cols[c.lower()]
                    elif isinstance(spec.y, list) and c in spec.y:
                        spec.y = [lower_cols[c.lower()] if y == c else y for y in spec.y]
                else:
                    errors.append(f"Column '{c}' not found in dataset schema.")

    # Type rules (basic validation)
    if not errors and spec.source == "dataset":
        if spec.chart_type == "histogram":
            if spec.x and ctx.schema[spec.x].semantic_type not in ["numeric", "datetime"]:
                errors.append(f"Histogram x-axis '{spec.x}' must be numeric or datetime.")
        elif spec.chart_type == "scatter":
            if spec.x and ctx.schema[spec.x].semantic_type not in ["numeric", "datetime", "categorical"]:
                errors.append(f"Scatter x-axis '{spec.x}' is invalid.")
            if isinstance(spec.y, str) and ctx.schema[spec.y].semantic_type != "numeric":
                errors.append(f"Scatter y-axis '{spec.y}' must be numeric.")
        elif spec.chart_type == "box":
            if isinstance(spec.y, str) and ctx.schema[spec.y].semantic_type != "numeric":
                errors.append(f"Box plot y-axis '{spec.y}' must be numeric.")
            if spec.x and ctx.schema[spec.x].nunique > 20:
                errors.append(f"Box plot x-axis '{spec.x}' has too many categories (>20).")
        elif spec.chart_type == "heatmap":
            num_cols = [c for c, info in ctx.schema.items() if info.semantic_type == "numeric"]
            if len(num_cols) < 2:
                errors.append("Heatmap requires at least 2 numeric columns.")

    if isinstance(spec.y, list) and len(spec.y) > 12:
        errors.append("Too many series (max 12).")

    return len(errors) == 0, errors, spec
