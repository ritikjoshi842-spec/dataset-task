-- Migration: 001_create_memories_table.sql
-- Purpose: Persistent, Intelligent Memory storage for the AI Dataset Analyser (Supabase PostgreSQL)

CREATE TABLE IF NOT EXISTS persistent_memories (
    id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(128) NOT NULL DEFAULT 'default_user',
    memory_type VARCHAR(50) NOT NULL CHECK (
        memory_type IN (
            'preference',
            'correction',
            'domain_knowledge',
            'instruction',
            'filter_rule',
            'insight'
        )
    ),
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
