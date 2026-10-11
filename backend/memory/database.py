import importlib
import os
import sqlite3
from datetime import datetime, timezone
from typing import List, Optional
import psycopg2
from psycopg2.extras import RealDictCursor

import backend.config
if not hasattr(backend.config, "get_database_url"):
    importlib.reload(backend.config)
from backend.config import get_database_url, sanitize_db_error
from backend.memory.models import MemoryRecord, MemorySystemStatus

CREATE_TABLE_POSTGRES_SQL = """
CREATE TABLE IF NOT EXISTS persistent_memories (
    id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(128) NOT NULL DEFAULT 'default_user',
    memory_type VARCHAR(50) NOT NULL,
    content TEXT NOT NULL,
    topic VARCHAR(120),
    target_entity VARCHAR(160),
    scope VARCHAR(50) NOT NULL DEFAULT 'global',
    source VARCHAR(50) NOT NULL DEFAULT 'user_explicit',
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0.9,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_persistent_memories_user_active
    ON persistent_memories (user_id, is_active, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_persistent_memories_type_topic
    ON persistent_memories (memory_type, topic);
CREATE INDEX IF NOT EXISTS idx_persistent_memories_target_entity
    ON persistent_memories (target_entity);
"""


def _row_to_record(row: dict) -> MemoryRecord:
    created_at = row.get("created_at")
    updated_at = row.get("updated_at")
    if isinstance(created_at, str):
        try:
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except Exception:
            created_at = datetime.now(timezone.utc)
    if isinstance(updated_at, str):
        try:
            updated_at = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        except Exception:
            updated_at = datetime.now(timezone.utc)

    return MemoryRecord(
        id=str(row["id"]),
        user_id=str(row.get("user_id") or "default_user"),
        memory_type=row.get("memory_type") or "preference",
        content=str(row["content"]),
        topic=row.get("topic"),
        target_entity=row.get("target_entity"),
        scope=row.get("scope") or "global",
        source=row.get("source") or "user_explicit",
        confidence=float(row.get("confidence") if row.get("confidence") is not None else 0.9),
        is_active=bool(row.get("is_active", True)),
        created_at=created_at or datetime.now(timezone.utc),
        updated_at=updated_at or datetime.now(timezone.utc),
    )


class SupabaseMemoryRepository:
    """PostgreSQL repository for persistent memories backed by Supabase."""

    def __init__(self, db_url: Optional[str] = None, connect_timeout: int = 6):
        self._explicit_url = db_url
        self.connect_timeout = connect_timeout
        self._schema_initialized = False
        self._last_status: Optional[MemorySystemStatus] = None

    @property
    def db_url(self) -> Optional[str]:
        return self._explicit_url or get_database_url()

    def _get_connection(self):
        url = self.db_url
        if not url:
            raise RuntimeError(
                "Supabase PostgreSQL credentials are not configured. "
                "Set DATABASE_URL or SUPABASE_DB_PASSWORD in .env or .streamlit/secrets.toml."
            )
        return psycopg2.connect(url, connect_timeout=self.connect_timeout)

    def ensure_schema(self) -> MemorySystemStatus:
        """Initializes the persistent_memories table if not already present."""
        url = self.db_url
        if not url:
            self._last_status = MemorySystemStatus(
                available=False,
                backend_type="supabase_postgres",
                message="Memory unavailable: Supabase database credentials not configured.",
                last_error="Set DATABASE_URL or SUPABASE_DB_PASSWORD in .env or .streamlit/secrets.toml.",
            )
            return self._last_status

        try:
            conn = self._get_connection()
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(CREATE_TABLE_POSTGRES_SQL)
                self._schema_initialized = True
                self._last_status = MemorySystemStatus(
                    available=True,
                    backend_type="supabase_postgres",
                    message="Connected to Supabase PostgreSQL",
                    last_error=None,
                )
            finally:
                conn.close()
        except Exception as e:
            clean_err = sanitize_db_error(e)
            self._last_status = MemorySystemStatus(
                available=False,
                backend_type="supabase_postgres",
                message="Memory temporarily unavailable (Supabase connection failed).",
                last_error=clean_err,
            )
        return self._last_status

    def get_status(self) -> MemorySystemStatus:
        if not self._schema_initialized or self._last_status is None:
            return self.ensure_schema()
        return self._last_status

    def list_memories(
        self, include_inactive: bool = False, user_id: str = "default_user"
    ) -> List[MemoryRecord]:
        status = self.get_status()
        if not status.available:
            return []

        query = """
            SELECT id, user_id, memory_type, content, topic, target_entity,
                   scope, source, confidence, is_active, created_at, updated_at
            FROM persistent_memories
            WHERE user_id = %s
        """
        params: list = [user_id]
        if not include_inactive:
            query += " AND is_active = TRUE"
        query += " ORDER BY updated_at DESC"

        try:
            conn = self._get_connection()
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query, tuple(params))
                    rows = cur.fetchall()
                self._last_status = MemorySystemStatus(
                    available=True,
                    backend_type="supabase_postgres",
                    message="Connected to Supabase PostgreSQL",
                )
                return [_row_to_record(dict(r)) for r in rows]
            finally:
                conn.close()
        except Exception as e:
            self._last_status = MemorySystemStatus(
                available=False,
                backend_type="supabase_postgres",
                message="Memory retrieval failed.",
                last_error=sanitize_db_error(e),
            )
            return []

    def get_memory(self, memory_id: str) -> Optional[MemoryRecord]:
        status = self.get_status()
        if not status.available:
            return None

        query = """
            SELECT id, user_id, memory_type, content, topic, target_entity,
                   scope, source, confidence, is_active, created_at, updated_at
            FROM persistent_memories
            WHERE id = %s
        """
        try:
            conn = self._get_connection()
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query, (memory_id,))
                    row = cur.fetchone()
                return _row_to_record(dict(row)) if row else None
            finally:
                conn.close()
        except Exception as e:
            self._last_status = MemorySystemStatus(
                available=False,
                backend_type="supabase_postgres",
                message="Memory lookup failed.",
                last_error=sanitize_db_error(e),
            )
            return None

    def create_memory(self, record: MemoryRecord) -> Optional[MemoryRecord]:
        status = self.get_status()
        if not status.available:
            return None

        now = datetime.now(timezone.utc)
        record.created_at = now
        record.updated_at = now

        query = """
            INSERT INTO persistent_memories (
                id, user_id, memory_type, content, topic, target_entity,
                scope, source, confidence, is_active, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, user_id, memory_type, content, topic, target_entity,
                      scope, source, confidence, is_active, created_at, updated_at
        """
        params = (
            record.id,
            record.user_id,
            record.memory_type,
            record.content,
            record.topic,
            record.target_entity,
            record.scope,
            record.source,
            record.confidence,
            record.is_active,
            record.created_at,
            record.updated_at,
        )
        try:
            conn = self._get_connection()
            try:
                with conn:
                    with conn.cursor(cursor_factory=RealDictCursor) as cur:
                        cur.execute(query, params)
                        row = cur.fetchone()
                return _row_to_record(dict(row)) if row else record
            finally:
                conn.close()
        except Exception as e:
            self._last_status = MemorySystemStatus(
                available=False,
                backend_type="supabase_postgres",
                message="Failed to store memory.",
                last_error=sanitize_db_error(e),
            )
            return None

    def update_memory(
        self,
        memory_id: str,
        content: Optional[str] = None,
        memory_type: Optional[str] = None,
        topic: Optional[str] = None,
        target_entity: Optional[str] = None,
        is_active: Optional[bool] = None,
        source: Optional[str] = None,
        confidence: Optional[float] = None,
    ) -> Optional[MemoryRecord]:
        status = self.get_status()
        if not status.available:
            return None

        sets = ["updated_at = %s"]
        params: list = [datetime.now(timezone.utc)]

        if content is not None:
            sets.append("content = %s")
            params.append(content)
        if memory_type is not None:
            sets.append("memory_type = %s")
            params.append(memory_type)
        if topic is not None:
            sets.append("topic = %s")
            params.append(topic)
        if target_entity is not None:
            sets.append("target_entity = %s")
            params.append(target_entity)
        if is_active is not None:
            sets.append("is_active = %s")
            params.append(is_active)
        if source is not None:
            sets.append("source = %s")
            params.append(source)
        if confidence is not None:
            sets.append("confidence = %s")
            params.append(confidence)

        params.append(memory_id)
        query = f"""
            UPDATE persistent_memories
            SET {", ".join(sets)}
            WHERE id = %s
            RETURNING id, user_id, memory_type, content, topic, target_entity,
                      scope, source, confidence, is_active, created_at, updated_at
        """
        try:
            conn = self._get_connection()
            try:
                with conn:
                    with conn.cursor(cursor_factory=RealDictCursor) as cur:
                        cur.execute(query, tuple(params))
                        row = cur.fetchone()
                return _row_to_record(dict(row)) if row else None
            finally:
                conn.close()
        except Exception as e:
            self._last_status = MemorySystemStatus(
                available=False,
                backend_type="supabase_postgres",
                message="Failed to update memory.",
                last_error=sanitize_db_error(e),
            )
            return None

    def delete_memory(self, memory_id: str) -> bool:
        status = self.get_status()
        if not status.available:
            return False

        query = "DELETE FROM persistent_memories WHERE id = %s"
        try:
            conn = self._get_connection()
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(query, (memory_id,))
                        deleted = cur.rowcount > 0
                return deleted
            finally:
                conn.close()
        except Exception as e:
            self._last_status = MemorySystemStatus(
                available=False,
                backend_type="supabase_postgres",
                message="Failed to delete memory.",
                last_error=sanitize_db_error(e),
            )
            return False


class SQLiteMemoryRepository:
    """Parameterized SQLite repository sharing the exact same interface as SupabaseMemoryRepository.
    Used for isolated cross-session unit/integration testing without requiring external network access."""

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._persistent_conn = sqlite3.connect(db_path, check_same_thread=False) if db_path == ":memory:" else None
        self.ensure_schema()

    def _get_conn(self) -> sqlite3.Connection:
        if self._persistent_conn is not None:
            self._persistent_conn.row_factory = sqlite3.Row
            return self._persistent_conn
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def ensure_schema(self) -> MemorySystemStatus:
        conn = self._get_conn()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS persistent_memories (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL DEFAULT 'default_user',
                    memory_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    topic TEXT,
                    target_entity TEXT,
                    scope TEXT NOT NULL DEFAULT 'global',
                    source TEXT NOT NULL DEFAULT 'user_explicit',
                    confidence REAL NOT NULL DEFAULT 0.9,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()
        finally:
            if self._persistent_conn is None:
                conn.close()
        return MemorySystemStatus(
            available=True,
            backend_type="sqlite_test",
            message="Connected to local SQLite test database",
        )

    def get_status(self) -> MemorySystemStatus:
        return MemorySystemStatus(
            available=True,
            backend_type="sqlite_test",
            message="Connected to local SQLite test database",
        )

    def list_memories(
        self, include_inactive: bool = False, user_id: str = "default_user"
    ) -> List[MemoryRecord]:
        query = """
            SELECT id, user_id, memory_type, content, topic, target_entity,
                   scope, source, confidence, is_active, created_at, updated_at
            FROM persistent_memories
            WHERE user_id = ?
        """
        params: list = [user_id]
        if not include_inactive:
            query += " AND is_active = 1"
        query += " ORDER BY updated_at DESC"

        conn = self._get_conn()
        try:
            cur = conn.execute(query, tuple(params))
            rows = cur.fetchall()
            return [_row_to_record(dict(r)) for r in rows]
        finally:
            if self._persistent_conn is None:
                conn.close()

    def get_memory(self, memory_id: str) -> Optional[MemoryRecord]:
        conn = self._get_conn()
        try:
            cur = conn.execute(
                "SELECT * FROM persistent_memories WHERE id = ?", (memory_id,)
            )
            row = cur.fetchone()
            return _row_to_record(dict(row)) if row else None
        finally:
            if self._persistent_conn is None:
                conn.close()

    def create_memory(self, record: MemoryRecord) -> Optional[MemoryRecord]:
        now_iso = datetime.now(timezone.utc).isoformat()
        conn = self._get_conn()
        try:
            conn.execute(
                """
                INSERT INTO persistent_memories (
                    id, user_id, memory_type, content, topic, target_entity,
                    scope, source, confidence, is_active, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.user_id,
                    record.memory_type,
                    record.content,
                    record.topic,
                    record.target_entity,
                    record.scope,
                    record.source,
                    record.confidence,
                    1 if record.is_active else 0,
                    now_iso,
                    now_iso,
                ),
            )
            conn.commit()
            return self.get_memory(record.id)
        finally:
            if self._persistent_conn is None:
                conn.close()

    def update_memory(
        self,
        memory_id: str,
        content: Optional[str] = None,
        memory_type: Optional[str] = None,
        topic: Optional[str] = None,
        target_entity: Optional[str] = None,
        is_active: Optional[bool] = None,
        source: Optional[str] = None,
        confidence: Optional[float] = None,
    ) -> Optional[MemoryRecord]:
        sets = ["updated_at = ?"]
        params: list = [datetime.now(timezone.utc).isoformat()]
        if content is not None:
            sets.append("content = ?")
            params.append(content)
        if memory_type is not None:
            sets.append("memory_type = ?")
            params.append(memory_type)
        if topic is not None:
            sets.append("topic = ?")
            params.append(topic)
        if target_entity is not None:
            sets.append("target_entity = ?")
            params.append(target_entity)
        if is_active is not None:
            sets.append("is_active = ?")
            params.append(1 if is_active else 0)
        if source is not None:
            sets.append("source = ?")
            params.append(source)
        if confidence is not None:
            sets.append("confidence = ?")
            params.append(confidence)
        params.append(memory_id)

        conn = self._get_conn()
        try:
            conn.execute(
                f"UPDATE persistent_memories SET {', '.join(sets)} WHERE id = ?",
                tuple(params),
            )
            conn.commit()
            return self.get_memory(memory_id)
        finally:
            if self._persistent_conn is None:
                conn.close()

    def delete_memory(self, memory_id: str) -> bool:
        conn = self._get_conn()
        try:
            cur = conn.execute(
                "DELETE FROM persistent_memories WHERE id = ?", (memory_id,)
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            if self._persistent_conn is None:
                conn.close()
