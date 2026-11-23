
import sqlite3
import os
import json


# =========================================================
# 1. DATABASE CONFIGURATION
# =========================================================

DATABASE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "data",
    "customers.db"
)

DATABASE_TIMEOUT = 30


# =========================================================
# 2. DATABASE CONNECTION
# =========================================================

def get_connection():
    """
    Create a database connection with consistent settings.

    Foreign-key enforcement is enabled for every connection.
    A busy timeout reduces temporary database-lock errors.
    """

    database_directory = os.path.dirname(DATABASE_PATH)

    os.makedirs(database_directory, exist_ok=True)

    connection = sqlite3.connect(
        DATABASE_PATH,
        timeout=DATABASE_TIMEOUT
    )

    connection.row_factory = sqlite3.Row

    # Enable foreign-key enforcement.
    connection.execute("PRAGMA foreign_keys = ON")

    # Wait for a locked database instead of failing immediately.
    connection.execute("PRAGMA busy_timeout = 5000")

    return connection


# =========================================================
# 3. DATABASE INDEXES
# =========================================================

def create_database_indexes(connection):
    """
    Create indexes to improve common database queries.
    """

    indexes = [
        """
        CREATE INDEX IF NOT EXISTS
        idx_loans_customer_id
        ON loans(customer_id)
        """,

        """
        CREATE INDEX IF NOT EXISTS
        idx_payments_loan_id
        ON payments(loan_id)
        """,

        """
        CREATE INDEX IF NOT EXISTS
        idx_agent_logs_customer_id
        ON agent_logs(customer_id)
        """,

        """
        CREATE INDEX IF NOT EXISTS
        idx_agent_logs_created_at
        ON agent_logs(created_at)
        """,

        """
        CREATE INDEX IF NOT EXISTS
        idx_loans_status
        ON loans(status)
        """,

        """
        CREATE INDEX IF NOT EXISTS
        idx_payments_status
        ON payments(status)
        """
    ]

    for index_sql in indexes:
        connection.execute(index_sql)


# =========================================================
# 4. AGENT EXECUTION LOGGING
# =========================================================

def log_agent_execution(
    customer_id,
    agent_name,
    action,
    result
):
    """
    Persist an agent execution event in SQLite.
    """

    connection = get_connection()

    try:

        serialized_result = json.dumps(
            result,
            default=str,
            ensure_ascii=False
        )

        with connection:

            connection.execute(
                """
                INSERT INTO agent_logs
                (
                    customer_id,
                    agent_name,
                    action,
                    result
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    customer_id,
                    agent_name,
                    action,
                    serialized_result
                )
            )

    finally:

        connection.close()


# =========================================================
# 5. RETRIEVE AGENT EXECUTION LOGS
# =========================================================

def get_agent_logs(
    customer_id=None,
    limit=100
):
    """
    Retrieve recent agent logs.

    Logs can optionally be filtered by customer ID.
    """

    if not isinstance(limit, int) or isinstance(limit, bool):
        raise ValueError("Limit must be an integer.")

    if limit < 1 or limit > 500:
        raise ValueError("Limit must be between 1 and 500.")

    connection = get_connection()

    try:

        if customer_id is None:

            rows = connection.execute(
                """
                SELECT *
                FROM agent_logs
                ORDER BY created_at DESC, log_id DESC
                LIMIT ?
                """,
                (limit,)
            ).fetchall()

        else:

            rows = connection.execute(
                """
                SELECT *
                FROM agent_logs
                WHERE customer_id = ?
                ORDER BY created_at DESC, log_id DESC
                LIMIT ?
                """,
                (
                    customer_id,
                    limit
                )
            ).fetchall()

        return [
            dict(row)
            for row in rows
        ]

    finally:

        connection.close()


# =========================================================
# 6. DATABASE INITIALIZATION
# =========================================================

def initialize_database():
    """
    Initialize database tables and indexes.

    Existing records are preserved.
    Demonstration data is inserted only when the
    customers table is empty.
    """

    connection = get_connection()

    try:

        with connection:

            cursor = connection.cursor()

            # ---------------------------------------------
            # CUSTOMERS TABLE
            # ---------------------------------------------

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS customers (

                    customer_id INTEGER PRIMARY KEY AUTOINCREMENT,

                    name TEXT NOT NULL,

                    email TEXT,

                    phone TEXT,

                    monthly_income REAL,

                    employment_status TEXT

                )
                """
            )

            # ---------------------------------------------
            # LOANS TABLE
            # ---------------------------------------------

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS loans (

                    loan_id INTEGER PRIMARY KEY AUTOINCREMENT,

                    customer_id INTEGER,

                    loan_amount REAL,

                    outstanding_amount REAL,

                    due_date TEXT,

                    interest_rate REAL,

                    status TEXT,

                    FOREIGN KEY(customer_id)
                    REFERENCES customers(customer_id)

                )
                """
            )

            # ---------------------------------------------
            # PAYMENTS TABLE
            # ---------------------------------------------

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS payments (

                    payment_id INTEGER PRIMARY KEY AUTOINCREMENT,

                    loan_id INTEGER,

                    amount REAL,

                    payment_date TEXT,

                    status TEXT,

                    FOREIGN KEY(loan_id)
                    REFERENCES loans(loan_id)

                )
                """
            )

            # ---------------------------------------------
            # AGENT LOGS TABLE
            # ---------------------------------------------

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_logs (

                    log_id INTEGER PRIMARY KEY AUTOINCREMENT,

                    customer_id INTEGER,

                    agent_name TEXT,

                    action TEXT,

                    result TEXT,

                    created_at TIMESTAMP
                    DEFAULT CURRENT_TIMESTAMP

                )
                """
            )

            # ---------------------------------------------
            # CREATE INDEXES
            # ---------------------------------------------

            create_database_indexes(connection)

            # ---------------------------------------------
            # INSERT DEMONSTRATION DATA
            # ---------------------------------------------

            cursor.execute(
                "SELECT COUNT(*) FROM customers"
            )

            customer_count = cursor.fetchone()[0]

            if customer_count == 0:

                customers = [

                    (
                        "Rahul Sharma",
                        "rahul@example.com",
                        "9000000001",
                        45000,
                        "Employed"
                    ),

                    (
                        "Priya Kumar",
                        "priya@example.com",
                        "9000000002",
                        60000,
                        "Employed"
                    ),

                    (
                        "Amit Verma",
                        "amit@example.com",
                        "9000000003",
                        30000,
                        "Self-employed"
                    ),

                    (
                        "Sneha Reddy",
                        "sneha@example.com",
                        "9000000004",
                        25000,
                        "Unemployed"
                    )

                ]

                cursor.executemany(
                    """
                    INSERT INTO customers
                    (
                        name,
                        email,
                        phone,
                        monthly_income,
                        employment_status
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    customers
                )

                loans = [

                    (
                        1,
                        100000,
                        75000,
                        "2026-10-15",
                        12,
                        "Overdue"
                    ),

                    (
                        2,
                        200000,
                        50000,
                        "2026-12-15",
                        10,
                        "Active"
                    ),

                    (
                        3,
                        80000,
                        60000,
                        "2026-10-20",
                        14,
                        "Overdue"
                    ),

                    (
                        4,
                        50000,
                        45000,
                        "2026-11-15",
                        16,
                        "Overdue"
                    )

                ]

                cursor.executemany(
                    """
                    INSERT INTO loans
                    (
                        customer_id,
                        loan_amount,
                        outstanding_amount,
                        due_date,
                        interest_rate,
                        status
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    loans
                )

                payments = [

                    (
                        1,
                        25000,
                        "2026-09-15",
                        "Paid"
                    ),

                    (
                        2,
                        50000,
                        "2026-10-15",
                        "Paid"
                    ),

                    (
                        3,
                        20000,
                        "2026-08-20",
                        "Paid"
                    ),

                    (
                        4,
                        5000,
                        "2026-09-15",
                        "Paid"
                    )

                ]

                cursor.executemany(
                    """
                    INSERT INTO payments
                    (
                        loan_id,
                        amount,
                        payment_date,
                        status
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    payments
                )

        print("Database initialized successfully!")

    finally:

        connection.close()


# =========================================================
# 7. DATABASE INTEGRITY CHECK
# =========================================================

def check_database_integrity():
    """
    Check SQLite database integrity and foreign-key violations.
    """

    connection = get_connection()

    try:

        integrity_result = connection.execute(
            "PRAGMA integrity_check"
        ).fetchall()

        foreign_key_violations = connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

        return {

            "integrity_check": [
                row[0]
                for row in integrity_result
            ],

            "foreign_key_violations": [
                tuple(row)
                for row in foreign_key_violations
            ],

            "database_healthy": (
                len(integrity_result) == 1
                and integrity_result[0][0] == "ok"
                and len(foreign_key_violations) == 0
            )

        }

    finally:

        connection.close()


# =========================================================
# 8. MAIN EXECUTION
# =========================================================

if __name__ == "__main__":

    initialize_database()

    result = check_database_integrity()

    print("\nDatabase Integrity Report:")

    print(
        json.dumps(
            result,
            indent=4
        )
    )
