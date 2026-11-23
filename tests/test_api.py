import importlib
import pytest

from fastapi.testclient import TestClient


@pytest.fixture
def api_client(test_database, monkeypatch):
    """
    Load the API after the temporary database has been configured.
    This prevents tests from modifying the real project database.
    """
    # Keep authentication enabled in tests, but use a dedicated test key.
    monkeypatch.setenv("DEBT_API_KEY", "test-only-api-key")

    import backend.api as api

    api = importlib.reload(api)

    with TestClient(
        api.app,
        headers={"X-API-Key": "test-only-api-key"}
    ) as client:
        yield client, api


def mock_workflow_result(customer_id):
    """Predictable workflow result for API testing."""

    customer_names = {
        1: "Rahul Sharma",
        2: "Priya Kumar"
    }

    communication = None

    if customer_id == 1:
        communication = {
            "customer_name": "Rahul Sharma",
            "customer_id": 1,
            "outstanding_amount": 75000,
            "loan_status": "Overdue",
            "message_draft": "This is a test communication draft.",
            "approval_status": "Pending Human Approval"
        }

    return {
        "customer_analysis": "Mock customer analysis",
        "payment_analysis": {"total_paid": 25000},
        "data_validation": {"validation_status": "PASSED"},
        "decision": {
            "customer_id": customer_id,
            "customer_name": customer_names.get(customer_id),
            "loan_id": 1 if customer_id == 1 else 2,
         "action": "prepare_overdue_reminder",
        "communication_required": customer_id == 1,
         "human_review_required": customer_id == 1
},
        "communication_draft": communication,
        "final_report": {
            "customer_id": customer_id,
            "customer_name": customer_names.get(customer_id),
            "analysis": "Mock report"
        },
        "errors": []
    }


# ==========================================
# 1. BASIC API TESTS
# ==========================================

def test_home_endpoint(api_client):
    client, api = api_client

    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["status"] == "online"


def test_health_endpoint(api_client):
    client, api = api_client

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert response.json()["database"] == "connected"


# ==========================================
# 2. CUSTOMER ENDPOINT TESTS
# ==========================================

def test_get_all_customers(api_client):
    client, api = api_client

    response = client.get("/customers")

    assert response.status_code == 200

    customers = response.json()

    assert len(customers) == 4
    assert customers[0]["name"] == "Rahul Sharma"


def test_get_customer_details(api_client):
    client, api = api_client

    response = client.get("/customers/1")

    assert response.status_code == 200

    data = response.json()

    assert data["customer"]["name"] == "Rahul Sharma"
    assert len(data["loans"]) == 1
    assert len(data["loans"][0]["payments"]) == 1


def test_get_missing_customer(api_client):
    client, api = api_client

    response = client.get("/customers/999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Customer not found"


# ==========================================
# 3. AGENT LOG TESTS
# ==========================================

def test_get_agent_logs(api_client):
    client, api = api_client

    api.get_agent_logs(
        customer_id=1,
        limit=100
    )

    response = client.get("/agent-logs")

    assert response.status_code == 200
    assert "logs" in response.json()


def test_agent_logs_limit_validation(api_client):
    client, api = api_client

    response = client.get("/agent-logs?limit=0")

    assert response.status_code == 422


# ==========================================
# 4. WORKFLOW API TESTS
# ==========================================

def test_analyze_customer(api_client, monkeypatch):
    client, api = api_client

    monkeypatch.setattr(
        api.workflow_app,
        "invoke",
        lambda state: mock_workflow_result(state["customer_id"])
    )

    response = client.post("/analyze/1")

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "completed"
    assert data["customer_id"] == 1
    assert data["communication_draft"] is not None
    assert data["final_report"] is not None


def test_analyze_missing_customer(api_client, monkeypatch):
    client, api = api_client

    workflow_called = {"value": False}

    def fake_invoke(state):
        workflow_called["value"] = True
        return mock_workflow_result(state["customer_id"])

    monkeypatch.setattr(
        api.workflow_app,
        "invoke",
        fake_invoke
    )

    response = client.post("/analyze/999")

    assert response.status_code == 404
    assert workflow_called["value"] is False


# ==========================================
# 5. COMMUNICATION APPROVAL TESTS
# ==========================================

def create_pending_approval(client, api, monkeypatch):
    """Create a pending approval using the analyze endpoint."""

    monkeypatch.setattr(
        api.workflow_app,
        "invoke",
        lambda state: mock_workflow_result(state["customer_id"])
    )

    response = client.post("/analyze/1")

    assert response.status_code == 200


def test_pending_communications(api_client, monkeypatch):
    client, api = api_client

    create_pending_approval(client, api, monkeypatch)

    response = client.get("/communications/pending")

    assert response.status_code == 200

    data = response.json()

    assert data["total_pending"] == 1
    assert data["communications"][0]["customer_name"] == "Rahul Sharma"


def test_approve_communication(api_client, monkeypatch):
    client, api = api_client

    create_pending_approval(client, api, monkeypatch)

    pending = client.get("/communications/pending").json()

    approval_id = pending["communications"][0]["approval_id"]

    response = client.post(
        f"/communications/{approval_id}/review",
        json={
            "decision": "approve",
            "reviewer_name": "Test Reviewer",
            "review_notes": "Approved during automated testing"
        }
    )

    assert response.status_code == 200

    data = response.json()

    assert data["review"]["approval_status"] == "Approved"
    assert data["communication_sent"] is False


def test_reject_communication(api_client, monkeypatch):
    client, api = api_client

    create_pending_approval(client, api, monkeypatch)

    pending = client.get("/communications/pending").json()

    approval_id = pending["communications"][0]["approval_id"]

    response = client.post(
        f"/communications/{approval_id}/review",
        json={
            "decision": "reject",
            "reviewer_name": "Test Reviewer",
            "review_notes": "Rejected during automated testing"
        }
    )

    assert response.status_code == 200
    assert response.json()["review"]["approval_status"] == "Rejected"


def test_duplicate_communication_review(api_client, monkeypatch):
    client, api = api_client

    create_pending_approval(client, api, monkeypatch)

    pending = client.get("/communications/pending").json()

    approval_id = pending["communications"][0]["approval_id"]

    payload = {
        "decision": "approve",
        "reviewer_name": "Test Reviewer"
    }

    first_response = client.post(
        f"/communications/{approval_id}/review",
        json=payload
    )

    second_response = client.post(
        f"/communications/{approval_id}/review",
        json=payload
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 409


def test_review_missing_approval(api_client):
    client, api = api_client

    response = client.post(
        "/communications/999/review",
        json={
            "decision": "approve",
            "reviewer_name": "Test Reviewer"
        }
    )

    assert response.status_code == 404


def test_invalid_review_request(api_client, monkeypatch):
    client, api = api_client

    create_pending_approval(client, api, monkeypatch)

    pending = client.get("/communications/pending").json()

    approval_id = pending["communications"][0]["approval_id"]

    response = client.post(
        f"/communications/{approval_id}/review",
        json={
            "decision": "invalid",
            "reviewer_name": "Test Reviewer"
        }
    )

    assert response.status_code == 422


# ==========================================
# 6. COMMUNICATION HISTORY TESTS
# ==========================================

def test_communication_history(api_client, monkeypatch):
    client, api = api_client

    create_pending_approval(client, api, monkeypatch)

    response = client.get("/communications/history")

    assert response.status_code == 200
    assert response.json()["total_records"] == 1


def test_communication_history_customer_filter(
    api_client, monkeypatch
):
    client, api = api_client

    create_pending_approval(client, api, monkeypatch)

    response = client.get(
        "/communications/history?customer_id=1"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["customer_id"] == 1
    assert data["total_records"] == 1


def test_communication_history_limit_validation(api_client):
    client, api = api_client

    response = client.get(
        "/communications/history?limit=0"
    )

    assert response.status_code == 422