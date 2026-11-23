from datetime import date

import pytest

import agents.communication as communication_module
from agents.communication import CommunicationAgent


class FrozenDate(date):
    """Fixed date for deterministic communication tests."""

    @classmethod
    def today(cls):
        return cls(2026, 11, 23)


@pytest.fixture
def communication_agent(test_database, monkeypatch):
    monkeypatch.setattr(
        communication_module,
        "date",
        FrozenDate
    )

    return CommunicationAgent()


def update_customer_loan(
    test_database,
    status,
    due_date,
    outstanding_amount=75000
):
    conn = test_database.get_connection()

    try:
        conn.execute(
            """
            UPDATE loans
            SET status = ?,
                due_date = ?,
                outstanding_amount = ?
            WHERE loan_id = 1
            """,
            (status, due_date, outstanding_amount)
        )

        conn.commit()

    finally:
        conn.close()


# ==========================================
# 1. CUSTOMER DATA RETRIEVAL
# ==========================================

def test_get_customer_data(communication_agent):
    result = communication_agent.get_customer_data(1)

    assert result is not None
    assert result["name"] == "Rahul Sharma"
    assert result["customer_id"] == 1
    assert result["loan_id"] == 1


def test_get_customer_data_missing_customer(communication_agent):
    result = communication_agent.get_customer_data(999)

    assert result is None


# ==========================================
# 2. OVERDUE LOAN COMMUNICATION
# ==========================================

def test_overdue_loan_with_due_date(
    communication_agent,
    test_database
):
    update_customer_loan(
        test_database,
        "Overdue",
        "2026-10-15"
    )

    result = communication_agent.generate_message(1)

    assert isinstance(result, dict)

    assert "overdue" in result["message_draft"].lower()

    assert "October 15, 2026" in result["message_draft"]


def test_overdue_loan_without_due_date(
    communication_agent,
    test_database
):
    update_customer_loan(
        test_database,
        "Overdue",
        None
    )

    result = communication_agent.generate_message(1)

    assert isinstance(result, dict)

    assert "due date is currently unavailable" in (
        result["message_draft"].lower()
    )


# ==========================================
# 3. ACTIVE LOAN DATE CONDITIONS
# ==========================================

def test_active_loan_with_past_due_date(
    communication_agent,
    test_database
):
    update_customer_loan(
        test_database,
        "Active",
        "2026-11-20"
    )

    result = communication_agent.generate_message(1)

    assert "Active" in result["message_draft"]

    assert "November 20, 2026" in result["message_draft"]

    assert "contact us if you need clarification" in (
        result["message_draft"].lower()
    )


def test_active_loan_due_today(
    communication_agent,
    test_database
):
    update_customer_loan(
        test_database,
        "Active",
        "2026-11-23"
    )

    result = communication_agent.generate_message(1)

    assert "recorded due date is today" in (
        result["message_draft"].lower()
    )


def test_active_loan_future_due_date(
    communication_agent,
    test_database
):
    update_customer_loan(
        test_database,
        "Active",
        "2026-12-15"
    )

    result = communication_agent.generate_message(1)

    assert "upcoming recorded due date" in (
        result["message_draft"].lower()
    )

    assert "December 15, 2026" in result["message_draft"]


def test_active_loan_without_due_date(
    communication_agent,
    test_database
):
    update_customer_loan(
        test_database,
        "Active",
        None
    )

    result = communication_agent.generate_message(1)

    assert "due date is currently unavailable" in (
        result["message_draft"].lower()
    )


def test_active_loan_with_invalid_due_date(
    communication_agent,
    test_database
):
    update_customer_loan(
        test_database,
        "Active",
        "invalid-date"
    )

    result = communication_agent.generate_message(1)

    assert isinstance(result, dict)

    assert "due date is currently unavailable" in (
        result["message_draft"].lower()
    )


# ==========================================
# 4. OUTSTANDING AMOUNT VALIDATION
# ==========================================

@pytest.mark.parametrize(
    "invalid_amount",
    ["invalid", None]
)
def test_invalid_outstanding_amount(
    communication_agent,
    test_database,
    invalid_amount
):
    update_customer_loan(
        test_database,
        "Overdue",
        "2026-10-15",
        invalid_amount
    )

    result = communication_agent.generate_message(1)

    assert result == (
        "Error: Invalid outstanding amount in database."
    )


# ==========================================
# 5. COMMUNICATION CONTENT VALIDATION
# ==========================================

def test_message_contains_repayment_information(
    communication_agent
):
    result = communication_agent.generate_message(1)

    message = result["message_draft"]

    assert "Rahul Sharma" in message
    assert "75,000.00" in message
    assert "repayment options" in message.lower()
    assert "contact us" in message.lower()


def test_message_requires_human_approval(
    communication_agent
):
    result = communication_agent.generate_message(1)

    assert (
        result["approval_status"]
        == "Pending Human Approval"
    )

    assert result["customer_id"] == 1
    assert result["loan_status"] == "Overdue"


def test_unknown_loan_status_with_missing_date(
    communication_agent,
    test_database
):
    update_customer_loan(
        test_database,
        "Unknown",
        None
    )

    result = communication_agent.generate_message(1)

    assert "Unknown" in result["message_draft"]

    assert "due date is currently unavailable" in (
        result["message_draft"].lower()
    )