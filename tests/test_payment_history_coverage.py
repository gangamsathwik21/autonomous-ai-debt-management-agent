import pytest

from agents.payment_history import PaymentHistoryAgent


@pytest.fixture
def payment_agent(test_database):
    return PaymentHistoryAgent()


def update_loan(
    test_database,
    loan_id,
    **fields
):
    allowed_fields = {
        "loan_amount",
        "outstanding_amount",
        "status"
    }

    assert set(fields).issubset(allowed_fields)

    conn = test_database.get_connection()

    try:
        assignments = ", ".join(
            f"{field} = ?" for field in fields
        )

        conn.execute(
            f"UPDATE loans SET {assignments} WHERE loan_id = ?",
            (*fields.values(), loan_id)
        )

        conn.commit()

    finally:
        conn.close()


def replace_payments(test_database, loan_id, payments):
    conn = test_database.get_connection()

    try:
        conn.execute(
            "DELETE FROM payments WHERE loan_id = ?",
            (loan_id,)
        )

        for payment in payments:
            conn.execute(
                """
                INSERT INTO payments
                (loan_id, amount, payment_date, status)
                VALUES (?, ?, ?, ?)
                """,
                (
                    loan_id,
                    payment["amount"],
                    payment["payment_date"],
                    payment["status"]
                )
            )

        conn.commit()

    finally:
        conn.close()


# ==========================================
# 1. PAYMENT DATA RETRIEVAL
# ==========================================

def test_get_payment_data(payment_agent):
    data = payment_agent.get_payment_data(1)

    assert data is not None
    assert data["loan"]["name"] == "Rahul Sharma"
    assert data["loan"]["loan_id"] == 1
    assert len(data["payments"]) == 1


def test_get_payment_data_missing_customer(payment_agent):
    result = payment_agent.get_payment_data(999)

    assert result is None


def test_payment_records_are_ordered_by_date(
    payment_agent,
    test_database
):
    replace_payments(
        test_database,
        1,
        [
            {
                "amount": 1000,
                "payment_date": "2026-09-20",
                "status": "Paid"
            },
            {
                "amount": 2000,
                "payment_date": "2026-08-15",
                "status": "Paid"
            }
        ]
    )

    data = payment_agent.get_payment_data(1)

    dates = [
        payment["payment_date"]
        for payment in data["payments"]
    ]

    assert dates == [
        "2026-08-15",
        "2026-09-20"
    ]


# ==========================================
# 2. FINANCIAL CALCULATIONS
# ==========================================

def test_calculate_payment_metrics(payment_agent):
    data = payment_agent.get_payment_data(1)

    metrics = payment_agent.calculate_payment_metrics(data)

    assert metrics["total_paid"] == 25000
    assert metrics["successful_payments"] == 1
    assert metrics["failed_payments"] == 0
    assert metrics["repayment_percentage"] == 25.0
    assert metrics["remaining_percentage"] == 75.0


def test_failed_and_pending_payment_calculation(
    payment_agent,
    test_database
):
    replace_payments(
        test_database,
        1,
        [
            {
                "amount": 10000,
                "payment_date": "2026-08-01",
                "status": "Paid"
            },
            {
                "amount": 5000,
                "payment_date": "2026-09-01",
                "status": "Failed"
            },
            {
                "amount": 3000,
                "payment_date": "2026-10-01",
                "status": "Pending"
            }
        ]
    )

    data = payment_agent.get_payment_data(1)

    metrics = payment_agent.calculate_payment_metrics(data)

    assert metrics["total_paid"] == 10000
    assert metrics["successful_payments"] == 1
    assert metrics["failed_payments"] == 1
    assert metrics["total_records"] == 3


def test_zero_original_loan_amount(
    payment_agent,
    test_database
):
    update_loan(
        test_database,
        1,
        loan_amount=0,
        outstanding_amount=0
    )

    data = payment_agent.get_payment_data(1)

    metrics = payment_agent.calculate_payment_metrics(data)

    assert metrics["repayment_percentage"] == 0
    assert metrics["remaining_percentage"] == 0


def test_no_payment_records(
    payment_agent,
    test_database
):
    replace_payments(test_database, 1, [])

    data = payment_agent.get_payment_data(1)

    metrics = payment_agent.calculate_payment_metrics(data)

    assert metrics["total_paid"] == 0
    assert metrics["successful_payments"] == 0
    assert metrics["failed_payments"] == 0
    assert metrics["total_records"] == 0


# ==========================================
# 3. REPORT OBSERVATIONS
# ==========================================

def test_report_identifies_failed_payments(
    payment_agent,
    test_database
):
    replace_payments(
        test_database,
        1,
        [
            {
                "amount": 5000,
                "payment_date": "2026-10-01",
                "status": "Failed"
            }
        ]
    )

    report = payment_agent.generate_report(1)

    assert any(
        "failed payments" in observation.lower()
        for observation in report["observations"]
    )


def test_report_identifies_outstanding_balance(
    payment_agent
):
    report = payment_agent.generate_report(1)

    assert any(
        "outstanding balance" in observation.lower()
        for observation in report["observations"]
    )


def test_report_identifies_overdue_status(
    payment_agent
):
    report = payment_agent.generate_report(1)

    assert any(
        "overdue" in observation.lower()
        for observation in report["observations"]
    )


def test_report_identifies_empty_payment_history(
    payment_agent,
    test_database
):
    replace_payments(test_database, 1, [])

    report = payment_agent.generate_report(1)

    assert any(
        "no payment records" in observation.lower()
        for observation in report["observations"]
    )


# ==========================================
# 4. REPORT LIMITATIONS
# ==========================================

def test_report_contains_all_data_limitations(
    payment_agent
):
    report = payment_agent.generate_report(1)

    assert len(report["limitations"]) == 3

    assert any(
        "repayment schedule" in item.lower()
        for item in report["limitations"]
    )

    assert any(
        "on time" in item.lower()
        for item in report["limitations"]
    )

    assert any(
        "interest accrual" in item.lower()
        for item in report["limitations"]
    )


# ==========================================
# 5. MISSING CUSTOMER
# ==========================================

def test_generate_report_missing_customer(payment_agent):
    result = payment_agent.generate_report(999)

    assert result is None