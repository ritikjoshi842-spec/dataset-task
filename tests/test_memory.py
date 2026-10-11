import os
import json
import pytest
import pandas as pd
from unittest.mock import MagicMock

from backend.config import sanitize_db_error
from backend.dataset import clean_and_profile_dataset
from backend.agent import DataAgent
from backend.report.builder import build_report_evidence, generate_report_draft
from backend.memory import (
    MemoryService,
    SQLiteMemoryRepository,
    SupabaseMemoryRepository,
    MemoryRecord,
)


@pytest.fixture
def sample_customer_ctx():
    df = pd.DataFrame(
        {
            "customer_id": ["C1", "C2", "C3", "C4", "C5"],
            "account_status": ["Active", "Cancelled", "Active", "Trial", "Active"],
            "net_revenue": [120.0, 0.0, 250.0, 50.0, 900.0],
            "signup_date": [
                "2024-01-05",
                "2024-01-12",
                "2024-01-19",
                "2024-01-26",
                "2024-02-02",
            ],
        }
    )
    return clean_and_profile_dataset("customer_accounts.csv", df)


@pytest.fixture
def sample_weather_ctx():
    df = pd.DataFrame(
        {
            "city": ["Tokyo", "Osaka", "Kyoto", "Sapporo"],
            "temperature_c": [18.5, 20.1, 17.8, 10.2],
            "humidity_pct": [60, 58, 65, 72],
        }
    )
    return clean_and_profile_dataset("weather_stations.csv", df)


def test_1_preference_saved_and_retrieved_across_sessions(tmp_path):
    """Scenario 1: A useful preference is saved in Session A and retrieved in a separate Session B."""
    db_file = str(tmp_path / "persistent_memories.db")

    # Session A: Save a preference
    session_a_service = MemoryService(repository=SQLiteMemoryRepository(db_file))
    cand, saved = session_a_service.process_user_turn(
        "Please remember that I always prefer median instead of mean for aggregations."
    )
    assert cand.action == "save"
    assert saved is not None
    assert saved.memory_type == "preference"
    assert saved.target_entity == "aggregation_metric"

    # Session B: Brand-new service & repository instance pointing to the same database
    session_b_service = MemoryService(repository=SQLiteMemoryRepository(db_file))
    memories, prompt_block, hints = session_b_service.retrieve_for_task(
        query="Compare typical net_revenue across account_status",
        task_type="chat",
    )
    assert len(memories) == 1
    assert "median" in memories[0].content.lower()
    assert hints["preferred_agg_func"] == "median"
    assert "PERSISTENT USER MEMORY" in prompt_block


def test_2_reusable_metric_definition_applied_to_later_analysis(tmp_path, sample_customer_ctx):
    """Scenario 2: A reusable metric definition is stored and injected into later analysis & report generation."""
    db_file = str(tmp_path / "metric_def.db")

    # Session 1: User defines 'active customers' and 'median' preference
    svc1 = MemoryService(repository=SQLiteMemoryRepository(db_file))
    cand1, _ = svc1.process_user_turn(
        "Remember that Active customers excludes cancelled accounts.",
        ctx=sample_customer_ctx,
    )
    assert cand1.action == "save"
    svc1.process_user_turn(
        "Remember that I always prefer median instead of mean.",
        ctx=sample_customer_ctx,
    )

    # Session 2: New session runs DataAgent and Report Builder
    svc2 = MemoryService(repository=SQLiteMemoryRepository(db_file))

    captured_messages = []
    mock_llm = MagicMock()

    def side_effect_chat(messages, tools=None, tool_choice="auto"):
        captured_messages.extend(messages)
        return {
            "role": "assistant",
            "content": json.dumps(
                {
                    "blocks": [
                        {
                            "type": "markdown",
                            "text": "**Active customers (excluding cancelled accounts) total 3.**",
                        }
                    ]
                }
            ),
        }

    mock_llm.chat.side_effect = side_effect_chat

    agent = DataAgent(llm_client=mock_llm, memory_service=svc2)
    resp, _ = agent.run(
        user_question="How many active customers do we have and what is their revenue?",
        ctx=sample_customer_ctx,
        history=[],
    )
    assert len(resp.blocks) == 1
    system_msg = captured_messages[0]["content"]
    assert "Active customers excludes cancelled accounts." in system_msg

    # Verify report builder also applies the median aggregation preference from memory
    evidence, _, _ = build_report_evidence(sample_customer_ctx, memory_service=svc2)
    agg_info = evidence["tool_results"]["aggregations"][0]
    assert agg_info["aggregation_function"] == "median"


def test_3_correction_updates_existing_memory_without_duplicate(tmp_path, sample_customer_ctx):
    """Scenario 3: A correction updates an existing memory instead of creating a contradictory duplicate."""
    db_file = str(tmp_path / "correction.db")
    svc = MemoryService(repository=SQLiteMemoryRepository(db_file))

    # Initial definition
    c1, m1 = svc.process_user_turn(
        "Remember that active customers excludes cancelled accounts.",
        ctx=sample_customer_ctx,
    )
    assert c1.action == "save"
    assert m1 is not None

    # User corrects the definition of active customers
    c2, m2 = svc.process_user_turn(
        "Actually, active customers excludes both cancelled and trial accounts.",
        ctx=sample_customer_ctx,
    )
    assert c2.action == "update"
    assert m2 is not None
    assert m2.id == m1.id
    assert "trial" in m2.content.lower()

    all_mems = svc.list_memories(include_inactive=True)
    assert len(all_mems) == 1
    assert "trial" in all_mems[0].content.lower()


def test_4_repeated_feedback_does_not_produce_duplicates(tmp_path):
    """Scenario 4: Repeated identical or near-identical feedback does not produce duplicate memories."""
    db_file = str(tmp_path / "dedup.db")
    svc = MemoryService(repository=SQLiteMemoryRepository(db_file))

    c1, _ = svc.process_user_turn("Remember that net revenue excludes refunded orders.")
    assert c1.action == "save"

    c2, _ = svc.process_user_turn("Please remember that net revenue excludes refunded orders!")
    assert c2.action == "ignore"

    assert len(svc.list_memories(include_inactive=True)) == 1


def test_5_one_time_questions_and_temp_instructions_not_saved(tmp_path, sample_customer_ctx):
    """Scenario 5: One-time dataset questions and temporary instructions are not saved as permanent memories."""
    db_file = str(tmp_path / "onetime.db")
    svc = MemoryService(repository=SQLiteMemoryRepository(db_file))

    # Standard dataset questions
    for q in [
        "What is the average net_revenue?",
        "Summarise this dataset for me",
        "Plot a bar chart of net_revenue by account_status",
        "Use median instead of mean for this report only",
        "Filter out cancelled accounts just for now",
    ]:
        cand, saved = svc.process_user_turn(q, ctx=sample_customer_ctx)
        assert cand.action == "ignore", f"Should have ignored one-time query: {q}"
        assert saved is None

    assert len(svc.list_memories(include_inactive=True)) == 0


def test_6_irrelevant_memories_not_injected(tmp_path, sample_customer_ctx, sample_weather_ctx):
    """Scenario 6: Irrelevant domain memories are not injected into unrelated requests."""
    db_file = str(tmp_path / "relevance.db")
    svc = MemoryService(repository=SQLiteMemoryRepository(db_file))

    svc.process_user_turn(
        "Remember that active customers excludes cancelled accounts.",
        ctx=sample_customer_ctx,
    )
    svc.process_user_turn(
        "Remember that net revenue excludes refunded orders.",
        ctx=sample_customer_ctx,
    )

    # Query on an unrelated weather dataset about temperature
    relevant, prompt_block, _ = svc.retrieve_for_task(
        query="What is the highest temperature_c across cities?",
        ctx=sample_weather_ctx,
        task_type="chat",
        wants_chart=False,
    )
    assert len(relevant) == 0
    assert prompt_block == ""


def test_7_edit_deactivate_delete_and_natural_language_forget(tmp_path):
    """Scenario 7: Editing, deactivating, reactivating, and deleting memories works correctly."""
    db_file = str(tmp_path / "crud.db")
    svc = MemoryService(repository=SQLiteMemoryRepository(db_file))

    rec, msg = svc.add_manual_memory(
        content="Prefer bar charts for category comparisons.",
        memory_type="preference",
        topic="visualization",
        target_entity="chart_preference",
    )
    assert rec is not None

    # Edit
    edited = svc.edit_memory(
        memory_id=rec.id,
        content="Prefer horizontal bar charts for category comparisons.",
        memory_type="preference",
        topic="visualization",
        target_entity="chart_preference",
    )
    assert edited is not None
    assert "horizontal" in edited.content.lower()

    # Deactivate temporarily -> should not appear in active retrieval
    svc.set_active(rec.id, False)
    active_list = svc.list_memories(include_inactive=False)
    assert len(active_list) == 0
    all_list = svc.list_memories(include_inactive=True)
    assert len(all_list) == 1 and not all_list[0].is_active

    # Reactivate
    svc.set_active(rec.id, True)
    assert len(svc.list_memories(include_inactive=False)) == 1

    # Natural language forget command
    cand, _ = svc.process_user_turn("Forget my old chart preference")
    assert cand.action == "delete"
    assert len(svc.list_memories(include_inactive=True)) == 0


def test_8_memory_failure_graceful_degradation(sample_customer_ctx):
    """Scenario 8: Memory retrieval/storage failure does not crash the existing application."""
    # Repository with an invalid unreachable URL
    broken_repo = SupabaseMemoryRepository(
        db_url="postgresql://postgres:secret_pw_123@invalid.host.local:5432/postgres",
        connect_timeout=1,
    )
    svc = MemoryService(repository=broken_repo)
    status = svc.get_status()
    assert status.available is False

    # Agent still runs without crashing
    mock_llm = MagicMock()
    mock_llm.chat.return_value = {
        "role": "assistant",
        "content": json.dumps({"blocks": [{"type": "markdown", "text": "Summary complete."}]}),
    }
    agent = DataAgent(llm_client=mock_llm, memory_service=svc)
    resp, _ = agent.run("Summarise the dataset", ctx=sample_customer_ctx, history=[])
    assert len(resp.blocks) == 1
    assert "Summary complete" in resp.blocks[0].text


def test_9_credentials_never_exposed_in_errors_or_memories(tmp_path):
    """Scenario 9: Database credentials and API keys are sanitized from error messages and blocked from memory storage."""
    raw_err = "connection to postgresql://postgres:MySuperSecretP@ss!@db.example-project.supabase.co:5432/postgres failed: password=MySuperSecretP@ss!"
    sanitized = sanitize_db_error(raw_err)
    assert "MySuperSecretP@ss!" not in sanitized
    assert "db.example-project.supabase.co" not in sanitized
    assert "[REDACTED]" in sanitized

    # Verify selector refuses to store connection strings or API keys
    db_file = str(tmp_path / "sec.db")
    svc = MemoryService(repository=SQLiteMemoryRepository(db_file))
    cand, saved = svc.process_user_turn(
        "Remember my database URL is postgresql://postgres:secret@db.example-project.supabase.co:5432/postgres"
    )
    assert cand.action == "ignore"
    assert saved is None
