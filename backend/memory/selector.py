import json
import re
import difflib
from typing import List, Optional
from backend.memory.models import MemoryCandidate, MemoryRecord, MemoryType
from backend.dataset import DatasetContext

# Patterns that must never be saved (credentials, secrets, connection strings)
SENSITIVE_PATTERNS = re.compile(
    r"(postgresql://|postgres://|gsk_[A-Za-z0-9]{15,}|sk-[A-Za-z0-9]{15,}|"
    r"api[_-]?key\s*[:=]|password\s*[:=]|secret\s*[:=]|bearer\s+[A-Za-z0-9_\-\.]+)",
    re.IGNORECASE,
)

# Patterns indicating a one-time / temporary instruction for the current turn only
ONE_TIME_PATTERNS = re.compile(
    r"\b(for this report|for this chart|just for now|this time only|only for this|"
    r"in this turn|right now only|for this question)\b",
    re.IGNORECASE,
)

# Explicit forget / remove memory commands
FORGET_PATTERNS = re.compile(
    r"^\s*(?:please\s+)?(?:forget|remove|delete|clear|drop|stop\s+remembering|stop\s+using)\s+"
    r"(?:that\s+|my\s+|the\s+)?(.+)$",
    re.IGNORECASE,
)

# Explicit remember / persist commands
EXPLICIT_REMEMBER_PATTERNS = re.compile(
    r"(?:^\s*(?:please\s+)?(?:remember|memorize|save\s+to\s+memory|keep\s+in\s+mind|note\s+that|always\s+remember)\b|"
    r"\b(?:from\s+now\s+on|in\s+all\s+future\s+analyses|across\s+all\s+sessions|always\s+use|i\s+always\s+prefer|i\s+prefer)\b)",
    re.IGNORECASE,
)

# Corrections & domain definitions
CORRECTION_PATTERNS = re.compile(
    r"(?:^\s*(?:actually|correction|no,|wait,|to\s+clarify|let\s+me\s+correct\s+that)\b|"
    r"\b(?:does\s+not\s+mean|instead\s+of\s+what\s+you\s+assumed|is\s+defined\s+as|excludes\b|includes\s+only\b|"
    r"stands\s+for\b|means\s+that\b|refers\s+to\b))",
    re.IGNORECASE,
)

# Purely analytical one-off question starters (when not accompanied by remember/correction/definition signals)
PURE_QUESTION_PATTERNS = re.compile(
    r"^\s*(?:what|how|why|when|where|who|which|show\s+me|plot|graph|chart|visualize|summarise|summarize|"
    r"list|count|calculate|compute|find|compare|tell\s+me|can\s+you|give\s+me)\b",
    re.IGNORECASE,
)


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _clean_memory_statement(raw_text: str) -> str:
    """Strips conversational prefixes ('Please remember that...') into a concise standalone statement."""
    cleaned = _normalize_whitespace(raw_text)
    cleaned = re.sub(
        r"^(?:hey\s*,?\s*|hi\s*,?\s*)?(?:please\s+)?(?:always\s+)?"
        r"(?:remember\s+that|remember\s*:|remember|memorize\s+that|keep\s+in\s+mind\s+that|"
        r"note\s+that|for\s+future\s+reference\s*,?|from\s+now\s+on\s*,?|"
        r"actually\s*,?|correction\s*:\s*|to\s+clarify\s*,?)\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()
    if cleaned and cleaned[0].islower():
        cleaned = cleaned[0].upper() + cleaned[1:]
    if cleaned and cleaned[-1] not in ".!?":
        cleaned += "."
    return cleaned


def _infer_target_entity_and_topic(text: str, ctx: Optional[DatasetContext] = None) -> tuple[Optional[str], Optional[str], MemoryType]:
    """Infers the canonical target_entity, topic, and memory_type from a statement."""
    lower = text.lower()

    # Check if any known dataset column is explicitly defined/corrected
    matched_col = None
    if ctx and ctx.schema:
        for col in ctx.schema.keys():
            if re.search(rf"\b{re.escape(col.lower())}\b", lower):
                matched_col = col.lower().replace(" ", "_")
                break

    # Check common domain entities ("X excludes Y", "X is defined as Y", "X means Y")
    domain_match = re.search(
        r"^([A-Za-z][A-Za-z0-9_\s]{1,35}?)\s+(?:excludes|includes\s+only|is\s+defined\s+as|means|refers\s+to|stands\s+for|=)\b",
        _clean_memory_statement(text),
        re.IGNORECASE,
    )
    extracted_subject = None
    if domain_match:
        subj = domain_match.group(1).strip().lower()
        # Strip leading articles
        subj = re.sub(r"^(?:the|our|a|an|metric|column|field|rule)\s+", "", subj).strip()
        if 2 <= len(subj) <= 35:
            extracted_subject = re.sub(r"\s+", "_", subj)

    # Check preference categories
    if any(k in lower for k in ("concise", "brief", "short report", "detailed report", "executive summary", "bullet")):
        return "report_style", "reporting", "preference"

    if any(k in lower for k in ("bar chart", "line chart", "scatter", "histogram", "box plot", "heatmap", "chart preference", "chart type", "graph")):
        return "chart_preference", "visualization", "preference"

    if any(k in lower for k in ("weekly", "monthly", "daily", "quarterly", "yearly", "granularity", "frequency")):
        if any(p in lower for p in ("prefer", "always", "use", "summary", "summaries", "group")):
            return "summary_frequency", "time_series", "preference"

    if any(k in lower for k in ("median", "mean", "average")) and any(p in lower for p in ("instead of", "prefer", "always use", "default to")):
        return "aggregation_metric", "statistics", "preference"

    if any(k in lower for k in ("filter", "where", "exclude", "only include")):
        entity = extracted_subject or matched_col or "filter_rule"
        topic = "filtering"
        if "customer" in lower or "account" in lower:
            topic = "customer_metrics"
        elif "revenue" in lower or "order" in lower or "sales" in lower or "refund" in lower:
            topic = "revenue"
        m_type: MemoryType = "correction" if re.search(r"^\s*(?:actually|no\b|correction\b|instead)", text, re.IGNORECASE) else (
            "domain_knowledge" if domain_match else "filter_rule"
        )
        return entity, topic, m_type

    if domain_match:
        entity = extracted_subject or matched_col
        topic = "domain_definitions"
        if entity and ("customer" in entity or "user" in entity or "account" in entity):
            topic = "customer_metrics"
        elif entity and ("revenue" in entity or "sales" in entity or "profit" in entity or "order" in entity):
            topic = "revenue"
        m_type = "correction" if re.search(r"^\s*(?:actually|no\b|correction\b)", text, re.IGNORECASE) else "domain_knowledge"
        return entity, topic, m_type

    if re.search(r"^\s*(?:actually|no\b|correction\b)", text, re.IGNORECASE):
        return extracted_subject or matched_col or "general_correction", "domain_definitions", "correction"

    if any(k in lower for k in ("prefer", "always", "never")):
        return extracted_subject or matched_col or "general_preference", "preferences", "preference"

    return extracted_subject or matched_col, "general", "instruction"


class MemorySelector:
    """Dedicated service responsible for identifying, evaluating, normalizing, deduplicating,
    and resolving conflicts for candidate memories."""

    def evaluate_turn(
        self,
        user_message: str,
        existing_memories: List[MemoryRecord],
        ctx: Optional[DatasetContext] = None,
        llm_client=None,
    ) -> MemoryCandidate:
        if not user_message or not user_message.strip():
            return MemoryCandidate(action="ignore", reason="Empty message.")

        text = _normalize_whitespace(user_message)

        # 1. Never store secrets, API keys, passwords, or connection strings
        if SENSITIVE_PATTERNS.search(text):
            return MemoryCandidate(
                action="ignore",
                reason="Message contains sensitive credentials or secret patterns.",
            )

        # 2. Check for explicit "Forget / Remove" memory commands first
        forget_match = FORGET_PATTERNS.match(text)
        if forget_match:
            target_phrase = forget_match.group(1).strip().lower().rstrip(".!?")
            matched_mem = self._find_memory_to_forget(target_phrase, existing_memories)
            if matched_mem:
                return MemoryCandidate(
                    action="delete",
                    target_memory_id=matched_mem.id,
                    memory_type=matched_mem.memory_type,
                    content=matched_mem.content,
                    topic=matched_mem.topic,
                    target_entity=matched_mem.target_entity,
                    reason=f"User explicitly requested to forget memory: {matched_mem.content}",
                )
            return MemoryCandidate(
                action="ignore",
                reason="User asked to forget a memory, but no matching active memory was found.",
            )

        has_explicit_remember = bool(EXPLICIT_REMEMBER_PATTERNS.search(text))
        has_correction_or_def = bool(CORRECTION_PATTERNS.search(text))
        is_one_time = bool(ONE_TIME_PATTERNS.search(text))

        # 3. Ignore one-time instructions unless user explicitly asks to remember permanently
        if is_one_time and not re.search(r"\b(remember|always|across sessions|in future)\b", text, re.IGNORECASE):
            return MemoryCandidate(
                action="ignore",
                reason="Instruction is scoped to the current one-time request/report only.",
            )

        # 4. Ignore normal one-off dataset questions ("What is the average cost?", "Plot a chart of sales")
        if not has_explicit_remember and not has_correction_or_def:
            if PURE_QUESTION_PATTERNS.match(text) or text.endswith("?"):
                return MemoryCandidate(
                    action="ignore",
                    reason="Standard one-time analytical question; not a reusable memory.",
                )
            # Also ignore short casual remarks that lack reusable signals
            return MemoryCandidate(
                action="ignore",
                reason="No explicit preference, domain definition, or correction detected.",
            )

        # 5. Normalize the statement and extract metadata
        normalized_content = _clean_memory_statement(text)
        target_entity, topic, mem_type = _infer_target_entity_and_topic(text, ctx=ctx)

        # Optional LLM refinement when statement is complex and llm_client is configured
        if llm_client and getattr(llm_client, "client", None) and len(text) > 120 and not target_entity:
            refined = self._llm_refine_candidate(text, llm_client)
            if refined and refined.get("action") == "ignore":
                return MemoryCandidate(action="ignore", reason=refined.get("reason", "LLM evaluated as non-reusable."))
            if refined and refined.get("content"):
                normalized_content = refined["content"]
                target_entity = refined.get("target_entity") or target_entity
                topic = refined.get("topic") or topic
                if refined.get("memory_type") in (
                    "preference", "correction", "domain_knowledge", "instruction", "filter_rule", "insight"
                ):
                    mem_type = refined["memory_type"]

        source = "user_correction" if mem_type == "correction" else (
            "user_explicit" if has_explicit_remember else "agent_inferred"
        )
        confidence = 0.98 if has_explicit_remember or mem_type == "correction" else 0.85

        # 6. Deduplication & Conflict Resolution against existing memories
        return self._deduplicate_or_resolve(
            normalized_content=normalized_content,
            mem_type=mem_type,
            topic=topic,
            target_entity=target_entity,
            source=source,
            confidence=confidence,
            existing_memories=existing_memories,
        )

    def _deduplicate_or_resolve(
        self,
        normalized_content: str,
        mem_type: MemoryType,
        topic: Optional[str],
        target_entity: Optional[str],
        source: str,
        confidence: float,
        existing_memories: List[MemoryRecord],
    ) -> MemoryCandidate:
        norm_lower = normalized_content.lower().rstrip(".!?").strip()

        for mem in existing_memories:
            existing_lower = mem.content.lower().rstrip(".!?").strip()

            # Check 1: Exact or near-exact duplicate text
            similarity = difflib.SequenceMatcher(None, norm_lower, existing_lower).ratio()
            if similarity >= 0.86:
                return MemoryCandidate(
                    action="ignore",
                    memory_type=mem.memory_type,
                    content=mem.content,
                    topic=mem.topic,
                    target_entity=mem.target_entity,
                    target_memory_id=mem.id,
                    reason="Equivalent memory already exists; skipping duplicate.",
                )

            # Check 2: Same target_entity (e.g. updating definition of 'active_customers' or 'chart_preference')
            if target_entity and mem.target_entity and target_entity.lower() == mem.target_entity.lower():
                updated_type: MemoryType = "correction" if mem_type == "correction" else mem.memory_type
                return MemoryCandidate(
                    action="update",
                    target_memory_id=mem.id,
                    memory_type=updated_type,
                    content=normalized_content,
                    topic=topic or mem.topic,
                    target_entity=target_entity,
                    source=source,
                    confidence=max(confidence, mem.confidence),
                    reason=f"Updated existing memory for '{target_entity}'.",
                )

        # New standalone memory
        return MemoryCandidate(
            action="save",
            memory_type=mem_type,
            content=normalized_content,
            topic=topic,
            target_entity=target_entity,
            source=source,
            confidence=confidence,
            reason="New reusable memory identified.",
        )

    def _find_memory_to_forget(
        self, target_phrase: str, existing_memories: List[MemoryRecord]
    ) -> Optional[MemoryRecord]:
        if not existing_memories:
            return None

        best_match: Optional[MemoryRecord] = None
        best_score = 0.0
        phrase_tokens = {
            w for w in re.findall(r"[a-z0-9_]+", target_phrase.lower())
            if w not in {"my", "old", "the", "rule", "about", "preference", "memory", "previous", "earlier"}
        }

        for mem in existing_memories:
            haystack = " ".join(
                filter(None, [mem.content, mem.topic, mem.target_entity, mem.memory_type])
            ).lower()
            hay_tokens = set(re.findall(r"[a-z0-9_]+", haystack))
            overlap = len(phrase_tokens & hay_tokens)
            score = overlap / max(len(phrase_tokens), 1)
            if mem.target_entity and mem.target_entity.replace("_", " ").lower() in target_phrase:
                score += 0.6
            if mem.topic and mem.topic.replace("_", " ").lower() in target_phrase:
                score += 0.4
            if score > best_score:
                best_score = score
                best_match = mem

        return best_match if best_score >= 0.35 else None

    def _llm_refine_candidate(self, user_text: str, llm_client) -> Optional[dict]:
        prompt = [
            {
                "role": "system",
                "content": (
                    "You extract reusable long-term memories from user feedback in a Data Analysis app. "
                    "Return JSON with keys: action ('save' or 'ignore'), memory_type "
                    "('preference', 'correction', 'domain_knowledge', 'instruction', 'filter_rule', 'insight'), "
                    "content (concise standalone rule), topic, target_entity, reason."
                ),
            },
            {"role": "user", "content": user_text},
        ]
        try:
            return llm_client.generate_json(prompt)
        except Exception:
            return None
