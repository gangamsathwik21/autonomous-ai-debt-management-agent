import pytest

from agents.customer_analysis import analyze_customer
from agents.payment_history import PaymentHistoryAgent
from agents.data_validation import DataValidationAgent
from agents.decision_agent import DecisionAgent
from agents.communication import CommunicationAgent
from agents.report_generation import ReportGenerationAgent


# ==========================================
# 1. CUSTOMER ANALYSIS AGENT
# ==========================================

def test_customer_analysis_returns_financial_report(test_database):
    report = analyze_customer(1)

    assert isinstance(report, str)
    assert "Rahul Sharma" in report
    assert "75,000.00" in report
    assert "25.00%" in report
    assert "Database-Recorded Loan Status" in report


def test_customer_analysis_handles_missing_customer(test_database):
    result = analyze_customer(999)

    assert result == "Customer not found in the database."


# ==========================================
# 2. PAYMENT HISTORY AGENT
# ==========================================

def test_payment_history_calculates_metrics(test_database):
    agent = PaymentHistoryAgent()

    report = agent.generate_report(1)

    metrics = report["financial_metrics"]

    assert report["customer_name"] == "Rahul Sharma"
    assert metrics["total_paid"] == 25000
    assert metrics["outstanding_amount"] == 75000
    assert metrics["successful_payments"] == 1
    assert metrics["failed_payments"] == 0
    assert metrics["repayment_percentage"] == 25.0
    assert metrics["remaining_percentage"] == 75.0


def test_payment_history_handles_missing_customer(test_database):
    agent = PaymentHistoryAgent()

    result = agent.generate_report(999)

    assert result is None


def test_payment_history_reports_data_limitations(test_database):
    agent = PaymentHistoryAgent()

    report = agent.generate_report(1)

    assert len(report["limitations"]) == 3
    assert any(
        "repayment schedule" in item.lower()
        for item in report["limitations"]
    )


# ==========================================
# 3. DATA VALIDATION AGENT
# ==========================================

def test_data_validation_passes_for_rahul(test_database):
    agent = DataValidationAgent()

    result = agent.validate_customer(1)

    assert result["validation_status"] == "PASSED"
    assert result["error_count"] == 0
    assert result["warning_count"] == 0


def test_data_validation_warns_for_priya(test_database):
    agent = DataValidationAgent()

    result = agent.validate_customer(2)

    assert result["validation_status"] == "WARNING"

    issue_codes = [
        issue["code"] for issue in result["issues"]
    ]

    assert "balance_reconciliation_mismatch" in issue_codes


def test_data_validation_handles_missing_customer(test_database):
    agent = DataValidationAgent()

    result = agent.validate_customer(999)

    assert result["validation_status"] == "FAILED"

    assert result["issues"][0]["code"] == "customer_not_found"


def test_data_validation_detects_invalid_payment():
    agent = DataValidationAgent()

    invalid_payment = [{
        "payment_id": 100,
        "amount": -500,
        "payment_date": "invalid-date",
        "status": "unknown"
    }]

    issues = agent.validate_payments(invalid_payment)

    issue_codes = [
        issue["code"] for issue in issues
    ]

    assert "invalid_payment_amount" in issue_codes
    assert "invalid_payment_date" in issue_codes
    assert "unknown_payment_status" in issue_codes


# ==========================================
# 4. DECISION AGENT
# ==========================================

def test_decision_agent_identifies_overdue_loan(test_database):
    agent = DecisionAgent()

    result = agent.make_decision(1)

    assert result["action"] == "prepare_overdue_reminder"
    assert result["priority"] == "High"
    assert result["communication_required"] is True
    assert result["human_review_required"] is True


def test_decision_agent_handles_missing_customer(test_database):
    agent = DecisionAgent()

    result = agent.make_decision(999)

    assert result["action"] == "manual_review"
    assert result["priority"] == "High"
    assert result["communication_required"] is False
    assert result["human_review_required"] is True


# ==========================================
# 5. COMMUNICATION AGENT
# ==========================================

def test_communication_agent_generates_draft(test_database):
    agent = CommunicationAgent()

    result = agent.generate_message(1)

    assert isinstance(result, dict)
    assert result["customer_name"] == "Rahul Sharma"
    assert result["outstanding_amount"] == 75000
    assert result["approval_status"] == "Pending Human Approval"

    assert "Rahul Sharma" in result["message_draft"]
    assert "75,000.00" in result["message_draft"]


def test_communication_agent_handles_missing_customer(test_database):
    agent = CommunicationAgent()

    result = agent.generate_message(999)

    assert result == "Customer not found."


# ==========================================
# 6. REPORT GENERATION AGENT
# ==========================================

def test_report_generation_uses_verified_metrics(
    test_database,
    monkeypatch
):
    agent = ReportGenerationAgent()

    # Mock the LLM response so the test doesn't call Ollama.
    monkeypatch.setattr(
        agent,
        "generate_ai_analysis",
        lambda facts: "Mock financial analysis for testing."
    )

    communication_draft = {
        "message_draft": "Test reminder",
        "approval_status": "Pending Human Approval"
    }

    report = agent.generate_report(
        1,
        communication_draft=communication_draft
    )

    assert report["customer_name"] == "Rahul Sharma"
    assert report["customer_id"] == 1

    assert report["financial_metrics"]["total_paid"] == 25000
    assert report["financial_metrics"]["outstanding"] == 75000

    assert report["analysis"] == "Mock financial analysis for testing."

    assert report["communication_draft"] == communication_draft


def test_report_generation_handles_missing_customer(
    test_database
):
    agent = ReportGenerationAgent()

    result = agent.generate_report(999)

    assert result is None