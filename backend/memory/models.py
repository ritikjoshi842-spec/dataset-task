import uuid
from datetime import datetime, timezone
from typing import Literal, Optional, List
from pydantic import BaseModel, Field

MemoryType = Literal[
    "preference",
    "correction",
    "domain_knowledge",
    "instruction",
    "filter_rule",
    "insight",
]

MemorySource = Literal[
    "user_explicit",
    "user_correction",
    "agent_inferred",
    "manual_ui",
]

MemoryScope = Literal["global", "dataset"]


class MemoryRecord(BaseModel):
    """Represents a single persistent memory record stored in Supabase PostgreSQL."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = Field(default="default_user", description="Owner scope for future multi-user support")
    memory_type: MemoryType = Field(default="preference", description="Category of the memory")
    content: str = Field(description="Concise, standalone, normalized memory statement")
    topic: Optional[str] = Field(default=None, description="Topic or category (e.g. reporting, customer_metrics)")
    target_entity: Optional[str] = Field(
        default=None,
        description="Associated metric, column name, or named rule (e.g. active_customers, net_revenue)",
    )
    scope: MemoryScope = Field(default="global", description="Whether reusable globally or dataset-specific")
    source: MemorySource = Field(default="user_explicit", description="How this memory was acquired")
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    is_active: bool = Field(default=True, description="Whether this memory is active for retrieval")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MemoryCandidate(BaseModel):
    """Output of the Memory Selection evaluation step."""

    action: Literal["save", "update", "delete", "ignore"] = Field(default="ignore")
    memory_type: Optional[MemoryType] = None
    content: Optional[str] = None
    topic: Optional[str] = None
    target_entity: Optional[str] = None
    scope: MemoryScope = "global"
    source: MemorySource = "user_explicit"
    confidence: float = 0.9
    target_memory_id: Optional[str] = None
    reason: str = ""


class MemorySystemStatus(BaseModel):
    """Represents the runtime health and availability of the persistent memory backend."""

    available: bool = True
    backend_type: str = "supabase_postgres"
    message: str = "Connected to Supabase PostgreSQL"
    last_error: Optional[str] = None
