
import pytest
import workflows.debt_workflow as workflow


@pytest.fixture
def workflow_database(test_database):
    """Use an isolated SQLite database for workflow tests."""
    return test_database


def test_safe_log_agent_success(monkeypatch):
    calls = []

    monkeypatch.setattr(
        workflow,
        "log_agent_execution",
        lambda *args: calls.append(args)
    )

    workflow.safe_log_agent(
        1, "Test Agent", "test_action", {"status": "SUCCESS"}
    )

    assert len(calls) == 1
    assert calls[0][0] == 1


def test_safe_log_agent_handles_logging_failure(monkeypatch):
    def failing_logger(*args):
        raise RuntimeError("Database logging failed")

    monkeypatch.setattr(
        workflow, "log_agent_execution", failing_logger
    )

    # Logging failure must not escape this function.
    workflow.safe_log_agent(
        1, "Test Agent", "test_action", {"status": "FAILED"}
    )


def test_customer_analysis_node_success(monkeypatch):
    monkeypatch.setattr(
        workflow,
        "analyze_customer",
        lambda customer_id: "Customer analysis completed"
    )

    result = workflow.customer_analysis_node({"customer_id": 1})

    assert result["customer_analysis"] == "Customer analysis completed"


def test_customer_analysis_node_failure(monkeypatch):
    def failing_analysis(customer_id):
        raise RuntimeError("Analysis failed")

    monkeypatch.setattr(
        workflow, "analyze_customer", failing_analysis
    )

    result = workflow.customer_analysis_node({"customer_id": 1})

    assert "Customer Analysis: Analysis failed" in result["errors"]


def test_payment_history_node_success(monkeypatch):
    monkeypatch.setattr(
        workflow.payment_agent,
        "generate_report",
        lambda customer_id: {"customer_name": "Rahul Sharma"}
    )

    result = workflow.payment_history_node({"customer_id": 1})

    assert result["payment_analysis"]["customer_name"] == "Rahul Sharma"


def test_payment_history_node_missing_data(monkeypatch):
    monkeypatch.setattr(
        workflow.payment_agent,
        "generate_report",
        lambda customer_id: None
    )

    result = workflow.payment_history_node({"customer_id": 1})

    assert any(
        "Customer not found in payment records" in error
        for error in result["errors"]
    )


def test_payment_history_node_exception(monkeypatch):
    def failing_report(customer_id):
        raise RuntimeError("Payment service failed")

    monkeypatch.setattr(
        workflow.payment_agent,
        "generate_report",
        failing_report
    )

    result = workflow.payment_history_node({"customer_id": 1})

    assert "Payment History: Payment service failed" in result["errors"]


def test_data_validation_node_success(monkeypatch):
    expected = {
        "validation_status": "PASSED",
        "total_issues": 0,
        "issues": []
    }

    monkeypatch.setattr(
        workflow.validation_agent,
        "validate_customer",
        lambda customer_id: expected
    )

    result = workflow.data_validation_node({"customer_id": 1})

    assert result["data_validation"] == expected


def test_data_validation_node_invalid_result(monkeypatch):
    monkeypatch.setattr(
        workflow.validation_agent,
        "validate_customer",
        lambda customer_id: None
    )

    result = workflow.data_validation_node({"customer_id": 1})

    assert result["data_validation"]["validation_status"] == "FAILED"
    assert "Data Validation: Invalid data validation result." in result["errors"]


def test_data_validation_node_exception(monkeypatch):
    def failing_validation(customer_id):
        raise RuntimeError("Validation engine failed")

    monkeypatch.setattr(
        workflow.validation_agent,
        "validate_customer",
        failing_validation
    )

    result = workflow.data_validation_node({"customer_id": 1})

    assert result["data_validation"]["validation_status"] == "FAILED"
    assert result["data_validation"]["issues"][0]["code"] == (
        "validation_agent_failure"
    )


def test_decision_node_validation_warning_blocks_communication(monkeypatch):
    monkeypatch.setattr(
        workflow.decision_agent,
        "get_customer_data",
        lambda customer_id: {
            "name": "Priya Kumar",
            "loan_id": 2,
            "status": "Active",
            "outstanding_amount": 50000,
            "due_date": "2026-12-15"
        }
    )

    result = workflow.decision_node({
        "customer_id": 2,
        "data_validation": {
            "validation_status": "WARNING",
            "issues": [{"message": "Balance discrepancy"}]
        }
    })

    assert result["decision"]["action"] == "manual_review"
    assert result["decision"]["priority"] == "High"
    assert result["decision"]["communication_required"] is False
    assert result["decision"]["human_review_required"] is True


def test_decision_node_validation_passed(monkeypatch):
    expected = {
        "customer_id": 1,
        "action": "prepare_overdue_reminder",
        "priority": "High",
        "communication_required": True
    }

    monkeypatch.setattr(
        workflow.decision_agent,
        "make_decision",
        lambda customer_id: expected.copy()
    )

    result = workflow.decision_node({
        "customer_id": 1,
        "data_validation": {"validation_status": "PASSED"}
    })

    assert result["decision"]["action"] == "prepare_overdue_reminder"
    assert result["decision"]["validation_status"] == "PASSED"


def test_decision_node_invalid_result(monkeypatch):
    monkeypatch.setattr(
        workflow.decision_agent,
        "make_decision",
        lambda customer_id: None
    )

    result = workflow.decision_node({
        "customer_id": 1,
        "data_validation": {"validation_status": "PASSED"}
    })

    assert result["decision"]["action"] == "manual_review"
    assert result["decision"]["human_review_required"] is True
    assert any("Invalid decision result" in e for e in result["errors"])


def test_route_after_decision_allows_communication():
    result = workflow.route_after_decision({
        "customer_id": 1,
        "data_validation": {"validation_status": "PASSED"},
        "decision": {"communication_required": True}
    })

    assert result == "communication"


def test_route_after_decision_blocks_warning():
    result = workflow.route_after_decision({
        "customer_id": 2,
        "data_validation": {"validation_status": "WARNING"},
        "decision": {"communication_required": True}
    })

    assert result == "report_generation"


def test_route_after_decision_blocks_when_not_required():
    result = workflow.route_after_decision({
        "customer_id": 1,
        "data_validation": {"validation_status": "PASSED"},
        "decision": {"communication_required": False}
    })

    assert result == "report_generation"


def test_communication_node_validation_failure(monkeypatch):
    def should_not_run(customer_id):
        pytest.fail("Communication should not be generated")

    monkeypatch.setattr(
        workflow.communication_agent,
        "generate_message",
        should_not_run
    )

    result = workflow.communication_node({
        "customer_id": 2,
        "data_validation": {"validation_status": "WARNING"},
        "decision": {"communication_required": True}
    })

    assert result["communication_draft"] is None


def test_communication_node_not_required(monkeypatch):
    def should_not_run(customer_id):
        pytest.fail("Communication should not be generated")

    monkeypatch.setattr(
        workflow.communication_agent,
        "generate_message",
        should_not_run
    )

    result = workflow.communication_node({
        "customer_id": 1,
        "data_validation": {"validation_status": "PASSED"},
        "decision": {"communication_required": False}
    })

    assert result["communication_draft"] is None


def test_communication_node_requires_human_approval(monkeypatch):
    monkeypatch.setattr(
        workflow.communication_agent,
        "generate_message",
        lambda customer_id: {
            "message_draft": "Payment reminder",
            "customer_name": "Rahul Sharma"
        }
    )

    result = workflow.communication_node({
        "customer_id": 1,
        "data_validation": {"validation_status": "PASSED"},
        "decision": {"communication_required": True}
    })

    assert result["communication_draft"]["approval_status"] == (
        "Pending Human Approval"
    )


def test_communication_node_handles_agent_failure(monkeypatch):
    def failing_message(customer_id):
        raise RuntimeError("Message generation failed")

    monkeypatch.setattr(
        workflow.communication_agent,
        "generate_message",
        failing_message
    )

    result = workflow.communication_node({
        "customer_id": 1,
        "data_validation": {"validation_status": "PASSED"},
        "decision": {"communication_required": True}
    })

    assert result["communication_draft"] is None
    assert any("Communication Agent" in e for e in result["errors"])


def test_communication_node_rejects_non_dictionary(monkeypatch):
    monkeypatch.setattr(
        workflow.communication_agent,
        "generate_message",
        lambda customer_id: "Invalid response"
    )

    result = workflow.communication_node({
        "customer_id": 1,
        "data_validation": {"validation_status": "PASSED"},
        "decision": {"communication_required": True}
    })

    assert result["communication_draft"] is None
    assert result["errors"]


def test_report_generation_node_success(monkeypatch):
    expected = {
        "customer_id": 1,
        "customer_name": "Rahul Sharma",
        "financial_metrics": {},
        "analysis": "Test analysis",
        "communication_draft": None
    }

    monkeypatch.setattr(
        workflow.report_agent,
        "generate_report",
        lambda customer_id, communication_draft=None: expected
    )

    result = workflow.report_generation_node({
        "customer_id": 1,
        "communication_draft": None
    })

    assert result["final_report"] == expected


def test_report_generation_node_missing_report(monkeypatch):
    monkeypatch.setattr(
        workflow.report_agent,
        "generate_report",
        lambda customer_id, communication_draft=None: None
    )

    result = workflow.report_generation_node({"customer_id": 1})

    assert "final_report" not in result
    assert any(
        "Unable to generate customer report" in error
        for error in result["errors"]
    )


def test_report_generation_node_exception(monkeypatch):
    def failing_report(customer_id, communication_draft=None):
        raise RuntimeError("Report service failed")

    monkeypatch.setattr(
        workflow.report_agent,
        "generate_report",
        failing_report
    )

    result = workflow.report_generation_node({"customer_id": 1})

    assert any("Report Generation: Report service failed" in e
               for e in result["errors"])
def test_run_debt_management_success(monkeypatch, capsys):
    class FakeApp:
        def invoke(self, initial_state):
            assert initial_state["customer_id"] == 1
            assert initial_state["errors"] == []

            return {
                "customer_analysis": "Customer analysis completed",
                "payment_analysis": {"total_paid": 25000},
                "data_validation": {
                    "validation_status": "PASSED",
                    "total_issues": 0,
                    "issues": []
                },
                "decision": {
                    "action": "prepare_overdue_reminder",
                    "priority": "High"
                },
                "communication_draft": {
                    "message_draft": "Sample reminder",
                    "approval_status": "Pending Human Approval"
                },
                "final_report": {
                    "customer_name": "Rahul Sharma",
                    "customer_id": 1,
                    "financial_metrics": {
                        "outstanding": 75000
                    },
                    "analysis": "Sample financial analysis",
                    "communication_draft": {
                        "message_draft": "Sample reminder",
                        "approval_status": "Pending Human Approval"
                    }
                },
                "errors": []
            }

    monkeypatch.setattr(
        workflow,
        "build_workflow",
        lambda: FakeApp()
    )

    workflow.run_debt_management(1)

    output = capsys.readouterr().out

    assert "Completed: 6" in output
    assert "Skipped: 0" in output
    assert "Failed: 0" in output
    assert "All workflow agents completed successfully." in output
    assert "Rahul Sharma" in output
    assert "Sample financial analysis" in output
    assert "Pending Human Approval" in output
def test_run_debt_management_with_skipped_communication(
    monkeypatch, capsys
):
    class FakeApp:
        def invoke(self, initial_state):
            return {
                "customer_analysis": "Completed",
                "payment_analysis": {},
                "data_validation": {
                    "validation_status": "WARNING",
                    "total_issues": 1,
                    "issues": [
                        {
                            "severity": "WARNING",
                            "message": "Outstanding balance mismatch"
                        }
                    ]
                },
                "decision": {
                    "action": "manual_review",
                    "priority": "High"
                },
                "communication_draft": None,
                "final_report": {
                    "customer_name": "Priya Kumar",
                    "customer_id": 2,
                    "financial_metrics": {},
                    "analysis": "Manual review required",
                    "communication_draft": None
                },
                "errors": []
            }

    monkeypatch.setattr(
        workflow,
        "build_workflow",
        lambda: FakeApp()
    )

    workflow.run_debt_management(2)

    output = capsys.readouterr().out

    assert "Skipped: 1" in output
    assert "Communication Agent: SKIPPED" in output
    assert "Workflow completed with intentional agent skips." in output
    assert "Outstanding balance mismatch" in output
    assert "No communication draft generated." in output
def test_run_debt_management_with_errors(monkeypatch, capsys):
    class FakeApp:
        def invoke(self, initial_state):
            return {
                "customer_analysis": None,
                "payment_analysis": None,
                "data_validation": None,
                "decision": None,
                "communication_draft": None,
                "final_report": None,
                "errors": [
                    "Customer Analysis: Database error",
                    "Communication Agent: Generation failed"
                ]
            }

    monkeypatch.setattr(
        workflow,
        "build_workflow",
        lambda: FakeApp()
    )

    workflow.run_debt_management(1)

    output = capsys.readouterr().out

    assert "Customer Analysis Agent: FAILED" in output
    assert "Payment History Agent: NOT_COMPLETED" in output
    assert "Data Validation Agent: NOT_COMPLETED" in output
    assert "Decision Agent: NOT_COMPLETED" in output
    assert "Communication Agent: FAILED" in output
    assert "Report Generation Agent: NOT_COMPLETED" in output

    assert "Failed: 2" in output
    assert "Not completed: 4" in output
    assert "Errors encountered:" in output
    assert "Final report could not be generated." in output
def test_run_debt_management_report_generation_failure(
    monkeypatch, capsys
):
    class FakeApp:
        def invoke(self, initial_state):
            return {
                "customer_analysis": "Completed",
                "payment_analysis": {},
                "data_validation": {
                    "validation_status": "PASSED",
                    "total_issues": 0,
                    "issues": []
                },
                "decision": {
                    "action": "monitor_account",
                    "priority": "Low"
                },
                "communication_draft": None,
                "final_report": None,
                "errors": [
                    "Report Generation: AI report failed"
                ]
            }

    monkeypatch.setattr(
        workflow,
        "build_workflow",
        lambda: FakeApp()
    )

    workflow.run_debt_management(1)

    output = capsys.readouterr().out

    assert "Report Generation Agent: FAILED" in output
    assert "Failed: 1" in output
    assert "AI report failed" in output
    assert "Final report could not be generated." in output
def test_run_debt_management_non_dictionary_communication(
    monkeypatch, capsys
):
    class FakeApp:
        def invoke(self, initial_state):
            return {
                "customer_analysis": "Completed",
                "payment_analysis": {},
                "data_validation": {
                    "validation_status": "PASSED",
                    "total_issues": 0,
                    "issues": []
                },
                "decision": {
                    "action": "monitor_account",
                    "priority": "Low"
                },
                "communication_draft": "Communication unavailable",
                "final_report": {
                    "customer_name": "Rahul Sharma",
                    "customer_id": 1,
                    "financial_metrics": {},
                    "analysis": "Sample analysis",
                    "communication_draft": "Communication unavailable"
                },
                "errors": []
            }

    monkeypatch.setattr(
        workflow,
        "build_workflow",
        lambda: FakeApp()
    )

    workflow.run_debt_management(1)

    output = capsys.readouterr().out

    assert "Communication unavailable" in output
    assert "Workflow completed with intentional agent skips." in output
    assert "Communication Agent: SKIPPED" in output

