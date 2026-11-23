import importlib
import json

import pytest
from fastapi.testclient import TestClient

import workflows.debt_workflow as debt_workflow


# ==========================================
# 1. TEST FIXTURES
# ==========================================

@pytest.fixture
def integration_client(test_database, monkeypatch):
    """
    Initialize FastAPI using the temporary test database.

    A test-only API key is configured before reloading the API module.
    Protected endpoints are exercised with normal authentication enabled.
    """

    # Configure authentication for this test process before importing/reloading
    # the API module, because the API reads this environment variable at request time.
    monkeypatch.setenv("DEBT_API_KEY", "test-only-api-key")

    import backend.api as api

    api = importlib.reload(api)

    # Send the test API key automatically to all protected endpoints.
    with TestClient(
        api.app,
        headers={"X-API-Key": "test-only-api-key"}
    ) as client:
        yield client, api


def mock_report_generation(
    customer_id,
    communication_draft=None
):
    """
    Mock only the Ollama report-generation operation.
    The actual workflow and other agents still execute.
    """

    customer_names = {
        1: "Rahul Sharma",
        2: "Priya Kumar",
        3: "Amit Verma",
        4: "Sneha Reddy"
    }

    return {
        "customer_id": customer_id,
        "customer_name": customer_names.get(customer_id),
        "financial_metrics": {
            "outstanding_amount": 75000
        },
        "analysis": "Mock AI financial analysis.",
        "communication_draft": communication_draft
    }


@pytest.fixture
def mock_ollama(monkeypatch):
    """
    Prevent actual local LLM inference during integration tests.
    """

    monkeypatch.setattr(
        debt_workflow.report_agent,
        "generate_report",
        mock_report_generation
    )


# ==========================================
# 2. REAL WORKFLOW + DATABASE TESTS
# ==========================================

def test_rahul_workflow_saves_communication_draft(
    integration_client,
    mock_ollama
):
    client, api = integration_client

    # Execute the actual FastAPI endpoint and LangGraph workflow.
    response = client.post("/analyze/1")

    assert response.status_code == 200

    data = response.json()

    # Verify workflow execution.
    assert data["status"] == "completed"

    assert data["data_validation"]["validation_status"] == "PASSED"

    assert data["decision"]["action"] == "prepare_overdue_reminder"

    assert data["communication_draft"] is not None

    # Verify communication approval status.
    assert (
        data["communication_draft"]["approval_status"]
        == "Pending Human Approval"
    )

    # Verify draft was saved in the actual SQLite test database.
    pending_response = client.get("/communications/pending")

    assert pending_response.status_code == 200

    pending = pending_response.json()

    assert pending["total_pending"] == 1

    assert (
        pending["communications"][0]["customer_name"]
        == "Rahul Sharma"
    )


def test_priya_validation_warning_blocks_database_draft(
    integration_client,
    mock_ollama
):
    client, api = integration_client

    response = client.post("/analyze/2")

    assert response.status_code == 200

    data = response.json()

    # Verify validation warning.
    assert data["data_validation"]["validation_status"] == "WARNING"

    # Verify manual review decision.
    assert data["decision"]["action"] == "manual_review"

    assert data["decision"]["human_review_required"] is True

    assert data["decision"]["communication_required"] is False

    # Verify communication was blocked.
    assert data["communication_draft"] is None

    # Verify no pending communication was stored.
    pending_response = client.get("/communications/pending")

    assert pending_response.status_code == 200

    assert pending_response.json()["total_pending"] == 0


# ==========================================
# 3. END-TO-END APPROVAL TEST
# ==========================================

def test_real_workflow_draft_can_be_approved(
    integration_client,
    mock_ollama
):
    client, api = integration_client

    # Step 1: Run the real workflow.
    analysis_response = client.post("/analyze/1")

    assert analysis_response.status_code == 200

    # Step 2: Retrieve the generated draft.
    pending_response = client.get("/communications/pending")

    pending = pending_response.json()

    assert pending["total_pending"] == 1

    approval_id = pending["communications"][0]["approval_id"]

    # Step 3: Approve the generated draft.
    approval_response = client.post(
        f"/communications/{approval_id}/review",
        json={
            "decision": "approve",
            "reviewer_name": "Integration Test Reviewer",
            "review_notes": "Approved during integration testing."
        }
    )

    assert approval_response.status_code == 200

    approval_data = approval_response.json()

    assert (
        approval_data["review"]["approval_status"]
        == "Approved"
    )

    # Approval must not send an actual message.
    assert approval_data["communication_sent"] is False

    # Step 4: Verify pending queue is empty.
    pending_after = client.get("/communications/pending")

    assert pending_after.json()["total_pending"] == 0

    # Step 5: Verify approval history.
    history_response = client.get("/communications/history")

    history = history_response.json()

    assert history["total_records"] == 1

    assert history["history"][0]["approval_status"] == "Approved"


# ==========================================
# 4. AGENT EXECUTION LOG TEST
# ==========================================

def test_real_workflow_persists_agent_execution_logs(
    integration_client,
    mock_ollama
):
    client, api = integration_client

    # Execute actual workflow.
    response = client.post("/analyze/1")

    assert response.status_code == 200

    # Retrieve logs from SQLite through FastAPI.
    logs_response = client.get("/agent-logs?customer_id=1")

    assert logs_response.status_code == 200

    logs_data = logs_response.json()

    assert logs_data["total_logs"] >= 6

    logs = logs_data["logs"]

    agent_names = {
        log["agent_name"]
        for log in logs
    }

    expected_agents = {
        "Customer Analysis Agent",
        "Payment History Agent",
        "Data Validation Agent",
        "Decision Agent",
        "Communication Agent",
        "Report Generation Agent"
    }

    assert expected_agents.issubset(agent_names)

    # Verify successful execution records.
    for log in logs:
        result = json.loads(log["result"])

        assert result["status"] in (
            "SUCCESS",
            "COMPLETED_MANUAL_REVIEW"
        )


# ==========================================
# 5. WORKFLOW SAFETY + AUDIT TEST
# ==========================================

def test_priya_communication_skip_is_logged(
    integration_client,
    mock_ollama
):
    client, api = integration_client

    response = client.post("/analyze/2")

    assert response.status_code == 200

    logs_response = client.get("/agent-logs?customer_id=2")

    assert logs_response.status_code == 200

    logs = logs_response.json()["logs"]

    communication_logs = [
        log for log in logs
        if log["agent_name"] == "Communication Agent"
    ]

    assert len(communication_logs) == 1

    result = json.loads(communication_logs[0]["result"])

    assert result["status"] == "SKIPPED"

    assert "validation" in result["reason"].lower()