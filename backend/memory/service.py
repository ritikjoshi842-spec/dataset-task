from typing import List, Optional, Literal, Tuple, Dict, Any
from backend.dataset import DatasetContext
from backend.memory.models import (
    MemoryRecord,
    MemoryCandidate,
    MemorySystemStatus,
    MemoryType,
)
from backend.memory.database import SupabaseMemoryRepository
from backend.memory.selector import (
    MemorySelector,
    SENSITIVE_PATTERNS,
    _clean_memory_statement,
    _infer_target_entity_and_topic,
)
from backend.memory.retriever import MemoryRetriever


class MemoryService:
    """High-level facade coordinating memory selection, database persistence, retrieval, and lifecycle management."""

    def __init__(self, repository=None, user_id: str = "default_user"):
        self.repository = repository or SupabaseMemoryRepository()
        self.selector = MemorySelector()
        self.retriever = MemoryRetriever()
        self.user_id = user_id

    def get_status(self) -> MemorySystemStatus:
        try:
            return self.repository.get_status()
        except Exception as e:
            return MemorySystemStatus(
                available=False,
                backend_type="supabase_postgres",
                message="Memory system encountered an unexpected error.",
                last_error=str(e),
            )

    def list_memories(self, include_inactive: bool = True) -> List[MemoryRecord]:
        try:
            return self.repository.list_memories(
                include_inactive=include_inactive, user_id=self.user_id
            )
        except Exception:
            return []

    def add_manual_memory(
        self,
        content: str,
        memory_type: MemoryType = "preference",
        topic: Optional[str] = None,
        target_entity: Optional[str] = None,
    ) -> Tuple[Optional[MemoryRecord], str]:
        """Explicitly adds or updates a memory from the UI or direct user action."""
        if not content or not content.strip():
            return None, "Memory content cannot be empty."
        if SENSITIVE_PATTERNS.search(content):
            return None, "Cannot store credentials, API keys, or sensitive secrets in memory."

        status = self.get_status()
        if not status.available:
            return None, status.last_error or status.message

        cleaned = _clean_memory_statement(content)
        inferred_entity, inferred_topic, _ = _infer_target_entity_and_topic(cleaned)
        final_entity = (target_entity.strip().lower().replace(" ", "_") if target_entity and target_entity.strip() else inferred_entity)
        final_topic = (topic.strip().lower().replace(" ", "_") if topic and topic.strip() else inferred_topic)

        existing = self.list_memories(include_inactive=False)
        cand = self.selector._deduplicate_or_resolve(
            normalized_content=cleaned,
            mem_type=memory_type,
            topic=final_topic,
            target_entity=final_entity,
            source="manual_ui",
            confidence=1.0,
            existing_memories=existing,
        )

        if cand.action == "ignore":
            return None, "An equivalent memory is already stored."
        elif cand.action == "update" and cand.target_memory_id:
            updated = self.repository.update_memory(
                memory_id=cand.target_memory_id,
                content=cleaned,
                memory_type=memory_type,
                topic=final_topic,
                target_entity=final_entity,
                source="manual_ui",
                confidence=1.0,
                is_active=True,
            )
            return updated, "Updated existing memory for the same rule/topic."

        record = MemoryRecord(
            user_id=self.user_id,
            memory_type=memory_type,
            content=cleaned,
            topic=final_topic,
            target_entity=final_entity,
            source="manual_ui",
            confidence=1.0,
            is_active=True,
        )
        created = self.repository.create_memory(record)
        if created:
            return created, "Memory saved to database."
        return None, "Failed to save memory to database."

    def edit_memory(
        self,
        memory_id: str,
        content: str,
        memory_type: Optional[MemoryType] = None,
        topic: Optional[str] = None,
        target_entity: Optional[str] = None,
    ) -> Optional[MemoryRecord]:
        if not content or not content.strip() or SENSITIVE_PATTERNS.search(content):
            return None
        cleaned = _clean_memory_statement(content)
        return self.repository.update_memory(
            memory_id=memory_id,
            content=cleaned,
            memory_type=memory_type,
            topic=topic,
            target_entity=target_entity,
        )

    def set_active(self, memory_id: str, is_active: bool) -> Optional[MemoryRecord]:
        return self.repository.update_memory(memory_id=memory_id, is_active=is_active)

    def delete_memory(self, memory_id: str) -> bool:
        return self.repository.delete_memory(memory_id=memory_id)

    def process_user_turn(
        self,
        user_message: str,
        ctx: Optional[DatasetContext] = None,
        llm_client=None,
    ) -> Tuple[MemoryCandidate, Optional[MemoryRecord]]:
        """Evaluates a user conversational turn and persists any new/updated/deleted memory."""
        status = self.get_status()
        if not status.available:
            return MemoryCandidate(action="ignore", reason="Memory database unavailable."), None

        existing = self.list_memories(include_inactive=False)
        cand = self.selector.evaluate_turn(
            user_message=user_message,
            existing_memories=existing,
            ctx=ctx,
            llm_client=llm_client,
        )

        if cand.action == "save" and cand.content:
            rec = MemoryRecord(
                user_id=self.user_id,
                memory_type=cand.memory_type or "preference",
                content=cand.content,
                topic=cand.topic,
                target_entity=cand.target_entity,
                scope=cand.scope,
                source=cand.source,
                confidence=cand.confidence,
                is_active=True,
            )
            saved = self.repository.create_memory(rec)
            return cand, saved

        elif cand.action == "update" and cand.target_memory_id and cand.content:
            updated = self.repository.update_memory(
                memory_id=cand.target_memory_id,
                content=cand.content,
                memory_type=cand.memory_type,
                topic=cand.topic,
                target_entity=cand.target_entity,
                source=cand.source,
                confidence=cand.confidence,
                is_active=True,
            )
            return cand, updated

        elif cand.action == "delete" and cand.target_memory_id:
            self.repository.delete_memory(cand.target_memory_id)
            return cand, None

        return cand, None

    def retrieve_for_task(
        self,
        query: str,
        ctx: Optional[DatasetContext] = None,
        task_type: Literal["chat", "chart", "report"] = "chat",
        wants_chart: bool = False,
        top_k: int = 6,
    ) -> Tuple[List[MemoryRecord], str, Dict[str, Any]]:
        """Retrieves relevant active memories, formats the LLM prompt context, and extracts tool hints."""
        status = self.get_status()
        if not status.available:
            return [], "", {"preferred_agg_func": None, "preferred_time_freq": None, "preferred_chart_type": None, "domain_rules": []}

        all_active = self.list_memories(include_inactive=False)
        relevant = self.retriever.retrieve(
            query=query,
            memories=all_active,
            ctx=ctx,
            task_type=task_type,
            wants_chart=wants_chart,
            top_k=top_k,
        )
        prompt_block = self.retriever.format_for_prompt(relevant)
        hints = self.retriever.extract_tool_hints(relevant)
        return relevant, prompt_block, hints


_default_memory_service: Optional[MemoryService] = None


def get_memory_service() -> MemoryService:
    global _default_memory_service
    if _default_memory_service is None:
        _default_memory_service = MemoryService()
    return _default_memory_service
