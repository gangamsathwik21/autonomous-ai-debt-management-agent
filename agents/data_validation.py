from datetime import datetime
from backend.database import get_connection


class DataValidationAgent:

    def __init__(self):
        self.name = "Data Validation Agent"

    # -----------------------------------------
    # 1. RETRIEVE CUSTOMER, LOAN AND PAYMENT DATA
    # -----------------------------------------

    def get_customer_data(self, customer_id):

        connection = get_connection()

        try:
            customer = connection.execute(
                """
                SELECT *
                FROM customers
                WHERE customer_id = ?
                """,
                (customer_id,)
            ).fetchone()

            if customer is None:
                return None

            loans = connection.execute(
                """
                SELECT *
                FROM loans
                WHERE customer_id = ?
                """,
                (customer_id,)
            ).fetchall()

            loan_details = []

            for loan in loans:

                payments = connection.execute(
                    """
                    SELECT *
                    FROM payments
                    WHERE loan_id = ?
                    ORDER BY payment_date
                    """,
                    (loan["loan_id"],)
                ).fetchall()

                loan_details.append({
                    "loan": dict(loan),
                    "payments": [
                        dict(payment) for payment in payments
                    ]
                })

            return {
                "customer": dict(customer),
                "loans": loan_details
            }

        finally:
            connection.close()

    # -----------------------------------------
    # 2. VALIDATE PAYMENT RECORDS
    # -----------------------------------------

    def validate_payments(self, payments):

        issues = []

        allowed_statuses = {
            "paid",
            "failed",
            "pending"
        }

        for payment in payments:

            payment_id = payment["payment_id"]

            try:
                amount = float(payment["amount"])

                if amount <= 0:
                    issues.append({
                        "severity": "ERROR",
                        "code": "invalid_payment_amount",
                        "message": (
                            f"Payment {payment_id} has a "
                            "zero or negative amount."
                        )
                    })

            except (TypeError, ValueError):
                issues.append({
                    "severity": "ERROR",
                    "code": "invalid_payment_amount",
                    "message": (
                        f"Payment {payment_id} has an "
                        "invalid amount."
                    )
                })

            status = str(payment["status"]).lower()

            if status not in allowed_statuses:

                issues.append({
                    "severity": "WARNING",
                    "code": "unknown_payment_status",
                    "message": (
                        f"Payment {payment_id} has an "
                        f"unrecognized status: {status}."
                    )
                })

            try:
                datetime.strptime(
                    payment["payment_date"],
                    "%Y-%m-%d"
                )

            except (ValueError, TypeError):
                issues.append({
                    "severity": "ERROR",
                    "code": "invalid_payment_date",
                    "message": (
                        f"Payment {payment_id} has an "
                        "invalid payment date."
                    )
                })

        return issues

    # -----------------------------------------
    # 3. VALIDATE LOAN INFORMATION
    # -----------------------------------------

    def validate_loan(self, loan, payments):

        issues = []

        try:
            original_loan = float(loan["loan_amount"])
            outstanding = float(loan["outstanding_amount"])

        except (TypeError, ValueError):

            return [{
                "severity": "ERROR",
                "code": "invalid_loan_amount",
                "message": "Loan amounts must be numeric."
            }]

        if original_loan <= 0:

            issues.append({
                "severity": "ERROR",
                "code": "invalid_original_loan",
                "message": "Original loan amount must be positive."
            })

        if outstanding < 0:

            issues.append({
                "severity": "ERROR",
                "code": "negative_outstanding",
                "message": "Outstanding balance cannot be negative."
            })

        if outstanding > original_loan:

            issues.append({
                "severity": "WARNING",
                "code": "outstanding_exceeds_original",
                "message": (
                    "Outstanding balance exceeds the original "
                    "loan amount. Verify interest and other charges."
                )
            })

        # Validate due date

        try:
            datetime.strptime(
                loan["due_date"],
                "%Y-%m-%d"
            )

        except (ValueError, TypeError):

            issues.append({
                "severity": "ERROR",
                "code": "invalid_due_date",
                "message": "Loan due date is invalid."
            })

        # Validate payment records

        issues.extend(
            self.validate_payments(payments)
        )

        # -------------------------------------
        # 4. CHECK FINANCIAL RECONCILIATION
        # -------------------------------------

        total_paid = 0.0

        for payment in payments:

            if str(payment["status"]).lower() == "paid":

                try:
                    amount = float(payment["amount"])

                    if amount > 0:
                        total_paid += amount

                except (TypeError, ValueError):
                    pass

        if original_loan > 0 and outstanding >= 0:

            expected_outstanding = (
                original_loan - total_paid
            )

            difference = abs(
                expected_outstanding - outstanding
            )

            if difference > 0.01:

                issues.append({
                    "severity": "WARNING",
                    "code": "balance_reconciliation_mismatch",
                    "message": (
                        "Recorded outstanding balance does not "
                        "match original loan minus successful "
                        "payments. "
                        f"Calculated balance: Rs. "
                        f"{expected_outstanding:,.2f}; "
                        f"recorded balance: Rs. "
                        f"{outstanding:,.2f}; "
                        f"difference: Rs. {difference:,.2f}. "
                        "This is a principal-only check. "
                        "Interest, fees, adjustments and missing "
                        "transactions may explain the difference."
                    )
                })

        return issues

    # -----------------------------------------
    # 5. RUN COMPLETE VALIDATION
    # -----------------------------------------

    def validate_customer(self, customer_id):

        data = self.get_customer_data(customer_id)

        if data is None:

            return {
                "customer_id": customer_id,
                "validation_status": "FAILED",
                "issues": [{
                    "severity": "ERROR",
                    "code": "customer_not_found",
                    "message": "Customer does not exist."
                }]
            }

        all_issues = []

        loans = data["loans"]

        if not loans:

            all_issues.append({
                "severity": "ERROR",
                "code": "no_loan_records",
                "message": "No loan records found for this customer."
            })

        for item in loans:

            loan = item["loan"]
            payments = item["payments"]

            loan_issues = self.validate_loan(
                loan,
                payments
            )

            for issue in loan_issues:

                issue["loan_id"] = loan["loan_id"]

            all_issues.extend(loan_issues)

        error_count = sum(
            1 for issue in all_issues
            if issue["severity"] == "ERROR"
        )

        warning_count = sum(
            1 for issue in all_issues
            if issue["severity"] == "WARNING"
        )

        if error_count > 0:
            status = "FAILED"

        elif warning_count > 0:
            status = "WARNING"

        else:
            status = "PASSED"

        return {
            "customer_id": customer_id,
            "customer_name": data["customer"]["name"],
            "validation_status": status,
            "total_loans_checked": len(loans),
            "total_issues": len(all_issues),
            "error_count": error_count,
            "warning_count": warning_count,
            "issues": all_issues
        }


# -----------------------------------------
# 6. STANDALONE TEST
# -----------------------------------------

if __name__ == "__main__":

    import json

    agent = DataValidationAgent()

    customer_id = int(
        input("Enter Customer ID (1-4): ")
    )

    result = agent.validate_customer(customer_id)

    print("\n====================================")
    print("       DATA VALIDATION REPORT")
    print("====================================")

    print(
        json.dumps(
            result,
            indent=4
        )
    )