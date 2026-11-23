from datetime import date

import pytest

import agents.decision_agent as decision_module
from agents.decision_agent import DecisionAgent


class FrozenDate(date):
    """Fixed date to make decision tests deterministic."""

    @classmethod
    def today(cls):
        return cls(2026, 11, 23)


@pytest.fixture
def decision_agent(test_database, monkeypatch):
    monkeypatch.setattr(decision_module, "date", FrozenDate)
    return DecisionAgent()


def update_loan(test_database, status, due_date):
    conn = test_database.get_connection()

    try:
        conn.execute(
            """
            UPDATE loans
            SET status = ?, due_date = ?
            WHERE loan_id = 1
            """,
            (status, due_date)
        )
        conn.commit()
    finally:
        conn.close()


def test_customer_not_found(decision_agent):
    result = decision_agent.make_decision(999)

    assert result["action"] == "manual_review"
    assert result["priority"] == "High"
    assert result["communication_required"] is False
    assert result["human_review_required"] is True


def test_overdue_loan(decision_agent, test_database):
    update_loan(test_database, "Overdue", "2026-10-15")

    result = decision_agent.make_decision(1)

    assert result["action"] == "prepare_overdue_reminder"
    assert result["priority"] == "High"
    assert result["communication_required"] is True
    assert result["human_review_required"] is True


@pytest.mark.parametrize("status", ["Closed", "Paid"])
def test_closed_or_paid_loan(decision_agent, test_database, status):
    update_loan(test_database, status, "2026-10-15")

    result = decision_agent.make_decision(1)

    assert result["action"] == "no_action_required"
    assert result["priority"] == "Low"
    assert result["communication_required"] is False
    assert result["human_review_required"] is False


@pytest.mark.parametrize("due_date", [None, "invalid-date"])
def test_active_loan_with_invalid_due_date(
    decision_agent,
    test_database,
    due_date
):
    update_loan(test_database, "Active", due_date)

    result = decision_agent.make_decision(1)

    assert result["action"] == "manual_review"
    assert result["priority"] == "High"
    assert result["communication_required"] is False
    assert result["human_review_required"] is True


def test_active_loan_with_past_due_date(decision_agent, test_database):
    update_loan(test_database, "Active", "2026-11-20")

    result = decision_agent.make_decision(1)

    assert result["action"] == "manual_review"
    assert result["days_since_due_date"] == 3
    assert result["human_review_required"] is True


@pytest.mark.parametrize(
    "due_date, expected_days",
    [
        ("2026-11-23", 0),
        ("2026-11-26", 3),
        ("2026-11-30", 7),
    ]
)
def test_upcoming_payment_reminder(
    decision_agent,
    test_database,
    due_date,
    expected_days
):
    update_loan(test_database, "Active", due_date)

    result = decision_agent.make_decision(1)

    assert result["action"] == "prepare_upcoming_reminder"
    assert result["priority"] == "Medium"
    assert result["days_remaining"] == expected_days
    assert result["communication_required"] is True
    assert result["human_review_required"] is True


def test_active_loan_more_than_seven_days_away(
    decision_agent,
    test_database
):
    update_loan(test_database, "Active", "2026-12-10")

    result = decision_agent.make_decision(1)

    assert result["action"] == "monitor_account"
    assert result["priority"] == "Low"
    assert result["days_remaining"] == 17
    assert result["communication_required"] is False
    assert result["human_review_required"] is False


def test_unknown_loan_status(decision_agent, test_database):
    update_loan(test_database, "Unknown", "2026-12-10")

    result = decision_agent.make_decision(1)

    assert result["action"] == "manual_review"
    assert result["priority"] == "High"
    assert result["communication_required"] is False
    assert result["human_review_required"] is True


def test_status_is_normalized(decision_agent, test_database):
    update_loan(test_database, "  OVERDUE  ", "2026-10-15")

    result = decision_agent.make_decision(1)

    assert result["action"] == "prepare_overdue_reminder"


def test_customer_data_retrieval(decision_agent):
    result = decision_agent.get_customer_data(1)

    assert result is not None
    assert result["customer_id"] == 1
    assert result["name"] == "Rahul Sharma"
    assert result["loan_id"] == 1