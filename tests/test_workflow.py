import json
import workflows.debt_workflow as workflow


def mock_report_generation(customer_id, communication_draft=None):
    """Return a predictable report without calling Ollama."""
    return {
        "customer_id": customer_id,
        "customer_name": "Rahul Sharma" if customer_id == 1 else "Priya Kumar",
        "financial_metrics": {
            "outstanding_amount": 75000
        },
        "analysis": "Mock financial analysis for workflow testing.",
        "communication_draft": communication_draft
    }


def prepare_workflow(monkeypatch):
    """Prevent actual LLM calls during workflow tests."""
    monkeypatch.setattr(
        workflow.report_agent,
        "generate_report",
        mock_report_generation
    )


def test_rahul_workflow_completes_with_communication(
    test_database, monkeypatch
):
    prepare_workflow(monkeypatch)

    app = workflow.build_workflow()

    result = app.invoke({
        "customer_id": 1,
        "errors": []
    })

    assert result["data_validation"]["validation_status"] == "PASSED"

    assert result["decision"]["action"] == "prepare_overdue_reminder"

    assert result["communication_draft"] is not None

    assert (
        result["communication_draft"]["approval_status"]
        == "Pending Human Approval"
    )

    assert result["final_report"] is not None

    assert result.get("errors", []) == []


def test_priya_workflow_blocks_communication(
    test_database, monkeypatch
):
    prepare_workflow(monkeypatch)

    app = workflow.build_workflow()

    result = app.invoke({
        "customer_id": 2,
        "errors": []
    })

    assert result["data_validation"]["validation_status"] == "WARNING"

    assert result["decision"]["action"] == "manual_review"

    assert result["decision"]["human_review_required"] is True

    assert result["decision"]["communication_required"] is False

    assert result.get("communication_draft") is None

    assert result["final_report"] is not None


def test_validation_failure_blocks_communication(
    test_database, monkeypatch
):
    prepare_workflow(monkeypatch)

    def failing_validation(customer_id):
        raise RuntimeError("Simulated validation failure")

    monkeypatch.setattr(
        workflow.validation_agent,
        "validate_customer",
        failing_validation
    )

    app = workflow.build_workflow()

    result = app.invoke({
        "customer_id": 1,
        "errors": []
    })

    assert result["data_validation"]["validation_status"] == "FAILED"

    assert result["decision"]["action"] == "manual_review"

    assert result["decision"]["communication_required"] is False

    assert result.get("communication_draft") is None

    assert any(
        "Data Validation" in error
        for error in result.get("errors", [])
    )


def test_communication_agent_failure_does_not_crash_workflow(
    test_database, monkeypatch
):
    prepare_workflow(monkeypatch)

    def failing_communication(customer_id):
        raise RuntimeError("Simulated communication failure")

    monkeypatch.setattr(
        workflow.communication_agent,
        "generate_message",
        failing_communication
    )

    app = workflow.build_workflow()

    result = app.invoke({
        "customer_id": 1,
        "errors": []
    })

    assert result.get("communication_draft") is None

    assert result["final_report"] is not None

    assert any(
        "Communication Agent" in error
        for error in result.get("errors", [])
    )


def test_report_generation_failure_is_recorded(
    test_database, monkeypatch
):
    def failing_report(customer_id, communication_draft=None):
        raise RuntimeError("Simulated report failure")

    monkeypatch.setattr(
        workflow.report_agent,
        "generate_report",
        failing_report
    )

    app = workflow.build_workflow()

    result = app.invoke({
        "customer_id": 1,
        "errors": []
    })

    assert result.get("final_report") is None

    assert any(
        "Report Generation" in error
        for error in result.get("errors", [])
    )


def test_missing_customer_does_not_generate_communication(
    test_database, monkeypatch
):
    prepare_workflow(monkeypatch)

    app = workflow.build_workflow()

    result = app.invoke({
        "customer_id": 999,
        "errors": []
    })

    assert result.get("communication_draft") is None

    assert result["decision"]["action"] == "manual_review"

    assert result["decision"]["communication_required"] is False