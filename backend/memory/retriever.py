import re
from typing import List, Optional, Literal, Dict, Any
from backend.memory.models import MemoryRecord
from backend.dataset import DatasetContext

STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "in", "on", "at", "to", "for", "of", "with", "by", "from", "about",
    "as", "into", "like", "through", "after", "over", "between", "out",
    "against", "during", "without", "before", "under", "around", "among",
    "and", "or", "but", "if", "while", "because", "that", "this", "these",
    "those", "what", "which", "who", "whom", "whose", "when", "where", "why",
    "how", "can", "could", "would", "should", "will", "shall", "may", "might",
    "do", "does", "did", "have", "has", "had", "me", "my", "your", "our",
    "please", "show", "tell", "give", "find", "use", "always", "prefer",
    "remember", "dataset", "data", "column", "columns", "row", "rows", "table",
}


def _stem_token(word: str) -> str:
    w = word.lower().strip()
    if len(w) > 5 and w.endswith("ing"):
        return w[:-3]
    if len(w) > 4 and w.endswith("ed"):
        return w[:-2]
    if len(w) > 4 and w.endswith("es"):
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def _tokenize(text: str) -> set[str]:
    if not text:
        return set()
    raw_words = re.findall(r"[a-z0-9]+", text.lower())
    return {_stem_token(w) for w in raw_words if w not in STOPWORDS and len(w) > 1}


class MemoryRetriever:
    """Retrieves and ranks relevant active memories for a given query, dataset context, and task."""

    def retrieve(
        self,
        query: str,
        memories: List[MemoryRecord],
        ctx: Optional[DatasetContext] = None,
        task_type: Literal["chat", "chart", "report"] = "chat",
        wants_chart: bool = False,
        top_k: int = 6,
        min_score: float = 0.20,
    ) -> List[MemoryRecord]:
        active_memories = [m for m in memories if m.is_active]
        if not active_memories:
            return []

        query_tokens = _tokenize(query)
        schema_tokens: set[str] = set()
        col_names_lower: set[str] = set()
        if ctx and ctx.schema:
            for col_name in ctx.schema.keys():
                col_names_lower.add(col_name.lower().replace(" ", "_"))
                schema_tokens |= _tokenize(col_name.replace("_", " "))

        scored: List[tuple[float, MemoryRecord]] = []

        for mem in active_memories:
            score = self._score_memory(
                mem=mem,
                query_lower=(query or "").lower(),
                query_tokens=query_tokens,
                schema_tokens=schema_tokens,
                col_names_lower=col_names_lower,
                task_type=task_type,
                wants_chart=wants_chart,
            )
            if score >= min_score:
                scored.append((score, mem))

        # Sort by relevance score descending, then by updated_at descending
        scored.sort(key=lambda item: (item[0], item[1].updated_at), reverse=True)
        return [item[1] for item in scored[:top_k]]

    def _score_memory(
        self,
        mem: MemoryRecord,
        query_lower: str,
        query_tokens: set[str],
        schema_tokens: set[str],
        col_names_lower: set[str],
        task_type: str,
        wants_chart: bool,
    ) -> float:
        score = 0.0
        mem_text = " ".join(filter(None, [mem.content, mem.topic, mem.target_entity]))
        mem_tokens = _tokenize(mem_text)
        entity_tokens = _tokenize((mem.target_entity or "").replace("_", " "))
        topic_tokens = _tokenize((mem.topic or "").replace("_", " "))

        # 1. Direct target_entity match in query or dataset columns
        if mem.target_entity:
            clean_entity = mem.target_entity.lower().replace("_", " ")
            if clean_entity in query_lower or mem.target_entity.lower() in col_names_lower:
                score += 0.65
            elif entity_tokens and (entity_tokens & (query_tokens | schema_tokens)):
                score += 0.45

        # 2. Keyword overlap between memory and current query
        if query_tokens and mem_tokens:
            q_overlap = len(query_tokens & mem_tokens)
            if q_overlap > 0:
                score += min(0.55, 0.22 * q_overlap)

        # 3. Keyword overlap between memory and current dataset schema columns
        if schema_tokens and (entity_tokens | topic_tokens):
            s_overlap = len(schema_tokens & (entity_tokens | topic_tokens))
            if s_overlap > 0:
                score += min(0.35, 0.18 * s_overlap)
        elif schema_tokens and mem_tokens and mem.memory_type in ("domain_knowledge", "correction", "filter_rule"):
            # Check if at least 2 domain tokens match the dataset schema
            s_content_overlap = len(schema_tokens & mem_tokens)
            if s_content_overlap >= 2:
                score += 0.28

        # 4. Task-level relevance for global preferences & instructions
        if mem.memory_type in ("preference", "instruction"):
            if mem.topic == "reporting" or mem.target_entity == "report_style":
                if task_type == "report" or any(w in query_lower for w in ("summary", "summarise", "summarize", "report", "overview", "explain", "insight")):
                    score += 0.35
                elif task_type == "chat":
                    # General communication style preference (e.g. concise answers)
                    if any(w in mem.content.lower() for w in ("concise", "brief", "bullet", "format", "tone", "style")):
                        score += 0.25
            elif mem.topic == "visualization" or mem.target_entity == "chart_preference":
                if wants_chart or task_type in ("chart", "report"):
                    score += 0.45
            elif mem.target_entity == "aggregation_metric" or mem.topic == "statistics":
                if task_type == "report" or any(
                    w in query_lower for w in ("average", "mean", "median", "typical", "summary", "summarise", "summarize", "compare", "stat")
                ):
                    score += 0.45
            elif mem.target_entity == "summary_frequency" or mem.topic == "time_series":
                if any(w in query_lower for w in ("time", "trend", "month", "week", "day", "year", "date", "period", "over time")) or "date" in schema_tokens:
                    score += 0.40

        # 5. Source priority multiplier (explicit corrections & user requests rank higher)
        if score > 0:
            if mem.source == "user_correction":
                score *= 1.15
            elif mem.source in ("user_explicit", "manual_ui"):
                score *= 1.08

        return round(score, 4)

    def extract_tool_hints(self, relevant_memories: List[MemoryRecord]) -> Dict[str, Any]:
        """Extracts actionable parameters from retrieved memories so tools and report builder
        can directly apply user preferences (e.g., median vs mean, weekly vs daily frequency, preferred chart type)."""
        hints: Dict[str, Any] = {
            "preferred_agg_func": None,
            "preferred_time_freq": None,
            "preferred_chart_type": None,
            "domain_rules": [],
        }
        for mem in relevant_memories:
            lower = mem.content.lower()
            if mem.target_entity == "aggregation_metric" or ("median" in lower and "mean" in lower):
                if "median" in lower and ("instead of mean" in lower or "prefer median" in lower or "use median" in lower):
                    hints["preferred_agg_func"] = "median"
                elif "mean" in lower and ("instead of median" in lower or "prefer mean" in lower or "use mean" in lower):
                    hints["preferred_agg_func"] = "mean"

            if mem.target_entity == "summary_frequency" or mem.topic == "time_series":
                if "weekly" in lower:
                    hints["preferred_time_freq"] = "W"
                elif "monthly" in lower:
                    hints["preferred_time_freq"] = "M"
                elif "quarterly" in lower:
                    hints["preferred_time_freq"] = "Q"
                elif "yearly" in lower or "annual" in lower:
                    hints["preferred_time_freq"] = "Y"
                elif "daily" in lower:
                    hints["preferred_time_freq"] = "D"

            if mem.target_entity == "chart_preference" or mem.topic == "visualization":
                for c_type in ("bar", "line", "scatter", "histogram", "box", "heatmap"):
                    if c_type in lower and not (f"instead of {c_type}" in lower or f"not {c_type}" in lower or f"avoid {c_type}" in lower):
                        hints["preferred_chart_type"] = c_type
                        break

            if mem.memory_type in ("domain_knowledge", "correction", "filter_rule"):
                hints["domain_rules"].append(mem.content)

        return hints

    def format_for_prompt(self, relevant_memories: List[MemoryRecord], max_chars: int = 1200) -> str:
        """Formats retrieved memories into a bounded, structured prompt block for LLM context injection."""
        if not relevant_memories:
            return ""

        lines = [
            "PERSISTENT USER MEMORY & DOMAIN RULES (Retrieved from long-term memory):",
            "Apply these rules, definitions, and preferences to your tool calls, calculations, and response formatting.",
            "Note: Treat these as contextual knowledge. If the user's explicit current instruction or the current dataset schema directly contradicts a stored memory, follow the current instruction/dataset and politely note the conflict.",
        ]
        used_chars = sum(len(line) for line in lines)

        for mem in relevant_memories:
            tag = mem.memory_type.upper()
            entity_str = f" [{mem.target_entity}]" if mem.target_entity else ""
            bullet = f"- ({tag}{entity_str}) {mem.content}"
            if used_chars + len(bullet) > max_chars:
                break
            lines.append(bullet)
            used_chars += len(bullet)

        return "\n".join(lines)
