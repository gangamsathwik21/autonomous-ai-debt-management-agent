import json


def test_database_tables_created(test_database):
    """Verify that all required database tables exist."""

    connection = test_database.get_connection()

    tables = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        """
    ).fetchall()

    table_names = [row["name"] for row in tables]

    connection.close()

    assert "customers" in table_names
    assert "loans" in table_names
    assert "payments" in table_names
    assert "agent_logs" in table_names


def test_demo_customers_inserted(test_database):
    """Verify that the expected synthetic customers are inserted."""

    connection = test_database.get_connection()

    customers = connection.execute(
        "SELECT * FROM customers ORDER BY customer_id"
    ).fetchall()

    connection.close()

    assert len(customers) == 4
    assert customers[0]["name"] == "Rahul Sharma"
    assert customers[1]["name"] == "Priya Kumar"


def test_database_initialization_does_not_duplicate_data(test_database):
    """Verify that repeated initialization doesn't duplicate customers."""

    test_database.initialize_database()
    test_database.initialize_database()

    connection = test_database.get_connection()

    customer_count = connection.execute(
        "SELECT COUNT(*) FROM customers"
    ).fetchone()[0]

    connection.close()

    assert customer_count == 4


def test_agent_execution_logging(test_database):
    """Verify that agent execution logs are stored and retrieved."""

    test_database.log_agent_execution(
        customer_id=1,
        agent_name="Customer Analysis Agent",
        action="Customer analysis completed",
        result={
            "status": "success",
            "outstanding_amount": 75000
        }
    )

    logs = test_database.get_agent_logs(customer_id=1)

    assert len(logs) == 1
    assert logs[0]["agent_name"] == "Customer Analysis Agent"

    result = json.loads(logs[0]["result"])

    assert result["status"] == "success"
    assert result["outstanding_amount"] == 75000


def test_agent_logs_can_be_filtered_by_customer(test_database):
    """Verify that logs are filtered by customer ID."""

    test_database.log_agent_execution(
        1, "Customer Analysis Agent", "Analysis", {"status": "success"}
    )

    test_database.log_agent_execution(
        2, "Payment History Agent", "Payment check", {"status": "success"}
    )

    logs = test_database.get_agent_logs(customer_id=1)

    assert len(logs) == 1
    assert logs[0]["customer_id"] == 1


def test_agent_logs_respect_limit(test_database):
    """Verify that the requested log limit is respected."""

    for index in range(3):
        test_database.log_agent_execution(
            1,
            "Test Agent",
            f"Action {index}",
            {"index": index}
        )

    logs = test_database.get_agent_logs(customer_id=1, limit=2)

    assert len(logs) == 2