from backend.database import get_connection
from datetime import datetime


# ==========================================
# PAYMENT HISTORY ANALYSIS AGENT
# ==========================================

class PaymentHistoryAgent:

    def __init__(self):
        self.name = "Payment History Agent"

    # ======================================
    # RETRIEVE CUSTOMER PAYMENT INFORMATION
    # ======================================

    def get_payment_data(self, customer_id):

        conn = get_connection()

        try:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT
                    c.customer_id,
                    c.name,
                    l.loan_id,
                    l.loan_amount,
                    l.outstanding_amount,
                    l.due_date,
                    l.status

                FROM customers c

                JOIN loans l
                ON c.customer_id = l.customer_id

                WHERE c.customer_id = ?
            """, (customer_id,))

            loan = cursor.fetchone()

            if loan is None:
                return None

            cursor.execute("""
                SELECT
                    payment_id,
                    amount,
                    payment_date,
                    status

                FROM payments

                WHERE loan_id = ?

                ORDER BY payment_date ASC
            """, (loan["loan_id"],))

            payments = cursor.fetchall()

            return {
                "loan": dict(loan),
                "payments": [dict(p) for p in payments]
            }

        finally:
            conn.close()

    # ======================================
    # PERFORM FINANCIAL CALCULATIONS
    # ======================================

    def calculate_payment_metrics(self, data):

        loan = data["loan"]
        payments = data["payments"]

        total_paid = sum(
            payment["amount"]
            for payment in payments
            if payment["status"].lower() == "paid"
        )

        successful_payments = sum(
            1 for payment in payments
            if payment["status"].lower() == "paid"
        )

        failed_payments = sum(
            1 for payment in payments
            if payment["status"].lower() == "failed"
        )

        original_loan = loan["loan_amount"]
        outstanding = loan["outstanding_amount"]

        repayment_percentage = (
            (total_paid / original_loan) * 100
            if original_loan > 0 else 0
        )

        # Compare recorded total paid with loan amount.
        # This is an indicative metric, not an amortization calculation.
        remaining_percentage = (
            (outstanding / original_loan) * 100
            if original_loan > 0 else 0
        )

        return {
            "customer_name": loan["name"],
            "loan_id": loan["loan_id"],
            "original_loan": original_loan,
            "outstanding_amount": outstanding,
            "total_paid": total_paid,
            "successful_payments": successful_payments,
            "failed_payments": failed_payments,
            "total_records": len(payments),
            "repayment_percentage": round(
                repayment_percentage, 2
            ),
            "remaining_percentage": round(
                remaining_percentage, 2
            ),
            "loan_status": loan["status"],
            "due_date": loan["due_date"]
        }

    # ======================================
    # GENERATE PAYMENT HISTORY REPORT
    # ======================================

    def generate_report(self, customer_id):

        data = self.get_payment_data(customer_id)

        if data is None:
            return None

        metrics = self.calculate_payment_metrics(data)

        report = {
            "agent": self.name,
            "customer_name": metrics["customer_name"],
            "loan_id": metrics["loan_id"],
            "financial_metrics": metrics,
            "payment_records": data["payments"],
            "observations": [],
            "limitations": []
        }

        # Identify observations
        if metrics["failed_payments"] > 0:
            report["observations"].append(
                "One or more failed payments are recorded."
            )

        if metrics["outstanding_amount"] > 0:
            report["observations"].append(
                "The loan has an outstanding balance."
            )

        if metrics["loan_status"].lower() == "overdue":
            report["observations"].append(
                "The database currently marks this loan as overdue."
            )

        if metrics["total_records"] == 0:
            report["observations"].append(
                "No payment records are available."
            )

        # Identify missing information
        report["limitations"].append(
            "The repayment schedule is not available."
        )

        report["limitations"].append(
            "Payment records alone cannot establish whether "
            "payments were made on time."
        )

        report["limitations"].append(
            "Interest accrual and additional charges are "
            "not included in these calculations."
        )

        return report


# ==========================================
# TEST THE AGENT
# ==========================================

if __name__ == "__main__":

    agent = PaymentHistoryAgent()

    print("\n" + "=" * 55)
    print("          PAYMENT HISTORY AI AGENT")
    print("=" * 55)

    try:

        customer_id = int(
            input("\nEnter Customer ID (1-4): ")
        )

        print("\nAnalysing repayment history...")

        report = agent.generate_report(customer_id)

        if report is None:

            print("\nCustomer not found.")

        else:

            metrics = report["financial_metrics"]

            print("\n" + "=" * 55)
            print("             PAYMENT ANALYSIS")
            print("=" * 55)

            print(
                f"\nCustomer: {report['customer_name']}"
            )

            print(
                f"Loan ID: {report['loan_id']}"
            )

            print(
                f"\nOriginal Loan Amount: "
                f"Rs. {metrics['original_loan']:,.2f}"
            )

            print(
                f"Total Amount Paid: "
                f"Rs. {metrics['total_paid']:,.2f}"
            )

            print(
                f"Outstanding Amount: "
                f"Rs. {metrics['outstanding_amount']:,.2f}"
            )

            print(
                f"Repayment Percentage: "
                f"{metrics['repayment_percentage']}%"
            )

            print(
                f"Successful Payments: "
                f"{metrics['successful_payments']}"
            )

            print(
                f"Failed Payments: "
                f"{metrics['failed_payments']}"
            )

            print(
                f"Total Payment Records: "
                f"{metrics['total_records']}"
            )

            print(
                f"Loan Status: "
                f"{metrics['loan_status']}"
            )

            print("\nOBSERVATIONS:")

            for observation in report["observations"]:
                print(f"- {observation}")

            print("\nDATA LIMITATIONS:")

            for limitation in report["limitations"]:
                print(f"- {limitation}")

            print("\n" + "=" * 55)

    except ValueError:

        print("\nPlease enter a valid customer ID.")

    except Exception as error:

        print(f"\nError: {error}")
