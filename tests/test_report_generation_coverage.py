import pytest

from agents.report_generation import ReportGenerationAgent


@pytest.fixture
def report_agent(test_database):
    return ReportGenerationAgent()


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


def update_loan(test_database, loan_id, **fields):
    allowed_fields = {
        "loan_amount",
        "outstanding_amount"
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


# ==========================================
# 1. CUSTOMER DATA RETRIEVAL
# ==========================================

def test_get_customer_data(report_agent):
    data = report_agent.get_customer_data(1)

    assert data is not None
    assert data["customer"]["name"] == "Rahul Sharma"
    assert data["customer"]["customer_id"] == 1
    assert data["customer"]["loan_id"] == 1
    assert len(data["payments"]) == 1


def test_get_customer_data_missing_customer(report_agent):
    result = report_agent.get_customer_data(999)

    assert result is None


def test_payment_records_ordered_by_date(
    report_agent,
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

    data = report_agent.get_customer_data(1)

    dates = [
        payment["payment_date"]
        for payment in data["payments"]
    ]

    assert dates == [
        "2026-08-15",
        "2026-09-20"
    ]


# ==========================================
# 2. FINANCIAL METRICS
# ==========================================

def test_calculate_metrics(report_agent):
    data = report_agent.get_customer_data(1)

    metrics = report_agent.calculate_metrics(data)

    assert metrics["total_paid"] == 25000
    assert metrics["outstanding"] == 75000
    assert metrics["successful_payments"] == 1
    assert metrics["failed_payments"] == 0
    assert metrics["total_records"] == 1
    assert metrics["repayment_percentage"] == 25.0
    assert metrics["outstanding_percentage"] == 75.0


def test_calculate_metrics_with_failed_and_pending_payments(
    report_agent,
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

    data = report_agent.get_customer_data(1)

    metrics = report_agent.calculate_metrics(data)

    assert metrics["total_paid"] == 10000
    assert metrics["successful_payments"] == 1
    assert metrics["failed_payments"] == 1
    assert metrics["total_records"] == 3


def test_zero_original_loan_amount(
    report_agent,
    test_database
):
    update_loan(
        test_database,
        1,
        loan_amount=0,
        outstanding_amount=0
    )

    data = report_agent.get_customer_data(1)

    metrics = report_agent.calculate_metrics(data)

    assert metrics["repayment_percentage"] == 0
    assert metrics["outstanding_percentage"] == 0


def test_no_payment_records(
    report_agent,
    test_database
):
    replace_payments(test_database, 1, [])

    data = report_agent.get_customer_data(1)

    metrics = report_agent.calculate_metrics(data)

    assert metrics["total_paid"] == 0
    assert metrics["successful_payments"] == 0
    assert metrics["failed_payments"] == 0
    assert metrics["total_records"] == 0


# ==========================================
# 3. FINANCIAL FACT PREPARATION
# ==========================================

def test_prepare_financial_facts(report_agent):
    data = report_agent.get_customer_data(1)

    metrics = report_agent.calculate_metrics(data)

    facts = report_agent.prepare_financial_facts(
        data,
        metrics
    )

    assert "Rahul Sharma" in facts
    assert "Original Loan Amount" in facts
    assert "Outstanding Amount" in facts
    assert "Database-Recorded Loan Status" in facts
    assert "Total Amount Paid" in facts
    assert "INDIVIDUAL PAYMENT RECORDS" in facts


def test_prepare_financial_facts_without_payments(
    report_agent,
    test_database
):
    replace_payments(test_database, 1, [])

    data = report_agent.get_customer_data(1)

    metrics = report_agent.calculate_metrics(data)

    facts = report_agent.prepare_financial_facts(
        data,
        metrics
    )

    assert "No payment records available." in facts


# ==========================================
# 4. AI ANALYSIS
# ==========================================

def test_generate_ai_analysis(
    report_agent,
    monkeypatch
):
    class MockResponse:
        content = "  Generated financial analysis.  "

    class MockLLM:
        def invoke(self, prompt):
            assert "STRICT RULES" in prompt
            assert "REPORT STRUCTURE" in prompt
            assert "Never invent financial information" in prompt

            return MockResponse()

    monkeypatch.setattr(
        report_agent,
        "llm",
        MockLLM()
    )

    result = report_agent.generate_ai_analysis(
        "Test financial facts"
    )

    assert result == "Generated financial analysis."


def test_generate_ai_analysis_uses_supplied_facts(
    report_agent,
    monkeypatch
):
    class MockResponse:
        content = "Analysis complete."

    class MockLLM:
        def invoke(self, prompt):
            assert "CUSTOMER_FACTS_123" in prompt
            return MockResponse()

    monkeypatch.setattr(
        report_agent,
        "llm",
        MockLLM()
    )

    result = report_agent.generate_ai_analysis(
        "CUSTOMER_FACTS_123"
    )

    assert result == "Analysis complete."


# ==========================================
# 5. CONSOLIDATED REPORT
# ==========================================

def test_generate_complete_report(report_agent):
    communication = {
        "message_draft": "Payment reminder draft.",
        "approval_status": "Pending Human Approval"
    }

    report = report_agent.generate_report(
        1,
        communication_draft=communication
    )

    assert report is not None
    assert report["customer_name"] == "Rahul Sharma"
    assert report["customer_id"] == 1
    assert report["analysis"] == "Mock AI financial analysis."
    assert report["communication_draft"] == communication


def test_generate_report_without_communication_draft(
    report_agent
):
    report = report_agent.generate_report(1)

    assert report is not None
    assert report["communication_draft"] is None


def test_generate_report_missing_customer(
    report_agent
):
    result = report_agent.generate_report(999)

    assert result is None


def test_generate_report_handles_ai_failure(
    report_agent,
    monkeypatch
):
    def raise_error(facts):
        raise RuntimeError("Ollama unavailable")

    monkeypatch.setattr(
        report_agent,
        "generate_ai_analysis",
        raise_error
    )

    report = report_agent.generate_report(1)

    assert report is not None
    assert "AI analysis could not be generated" in report["analysis"]
    assert "Ollama unavailable" in report["analysis"]
def test_generate_complete_report(report_agent, monkeypatch):
    monkeypatch.setattr(
        report_agent,
        "generate_ai_analysis",
        lambda facts: "Mock AI financial analysis."
    )

    communication = {
        "message_draft": "Payment reminder draft.",
        "approval_status": "Pending Human Approval"
    }

    report = report_agent.generate_report(
        1,
        communication_draft=communication
    )

    assert report is not None
    assert report["customer_name"] == "Rahul Sharma"
    assert report["customer_id"] == 1
    assert report["analysis"] == "Mock AI financial analysis."
    assert report["communication_draft"] == communication


def test_generate_report_without_communication_draft(
    report_agent,
    monkeypatch
):
    monkeypatch.setattr(
        report_agent,
        "generate_ai_analysis",
        lambda facts: "Mock AI financial analysis."
    )

    report = report_agent.generate_report(1)

    assert report is not None
    assert report["communication_draft"] is None    