
from datetime import date, datetime

from backend.database import get_connection


class CommunicationAgent:

    def __init__(self):
        self.name = "Communication Agent"

    # -----------------------------------------
    # 1. RETRIEVE CUSTOMER INFORMATION
    # -----------------------------------------

    def get_customer_data(self, customer_id):

        conn = get_connection()

        try:
            cursor = conn.cursor()

            cursor.execute("""
                SELECT
                    c.customer_id,
                    c.name,
                    c.email,
                    c.monthly_income,
                    c.employment_status,
                    l.loan_id,
                    l.outstanding_amount,
                    l.due_date,
                    l.status
                FROM customers c
                JOIN loans l
                ON c.customer_id = l.customer_id
                WHERE c.customer_id = ?
            """, (customer_id,))

            result = cursor.fetchone()

            if result is None:
                return None

            return dict(result)

        finally:
            conn.close()

    # -----------------------------------------
    # 2. GENERATE COMMUNICATION DRAFT
    # -----------------------------------------

    def generate_message(self, customer_id):

        customer = self.get_customer_data(customer_id)

        if customer is None:
            return "Customer not found."

        today = date.today()

        # Safely convert outstanding amount
        try:
            outstanding_amount = float(
                customer["outstanding_amount"]
            )
        except (ValueError, TypeError):
            return "Error: Invalid outstanding amount in database."

        # Format outstanding amount
        formatted_amount = f"Rs. {outstanding_amount:,.2f}"

        # -------------------------------------
        # Determine due date
        # -------------------------------------

        due_date = None

        try:
            if customer["due_date"]:
                due_date = datetime.strptime(
                    str(customer["due_date"]),
                    "%Y-%m-%d"
                ).date()

        except (ValueError, TypeError):
            due_date = None

        # -------------------------------------
        # Determine loan status and date message
        # -------------------------------------

        loan_status = str(customer["status"]).lower()

        if loan_status == "overdue":

            status_message = (
                "Our records show that your loan is currently "
                "marked as overdue."
            )

            if due_date:
                date_message = (
                    f"The recorded due date was "
                    f"{due_date.strftime('%B %d, %Y')}."
                )
            else:
                date_message = (
                    "The due date is currently unavailable "
                    "in our records."
                )

        elif due_date and due_date < today:

            status_message = (
                f"Our records show the loan status as "
                f"{customer['status']}."
            )

            date_message = (
                f"The recorded due date was "
                f"{due_date.strftime('%B %d, %Y')}. "
                "Please contact us if you need clarification."
            )

        elif due_date and due_date == today:

            status_message = (
                f"Our records show the loan status as "
                f"{customer['status']}."
            )

            date_message = "The recorded due date is today."

        elif due_date and due_date > today:

            status_message = (
                f"Our records show the loan status as "
                f"{customer['status']}."
            )

            date_message = (
                f"The upcoming recorded due date is "
                f"{due_date.strftime('%B %d, %Y')}."
            )

        else:

            status_message = (
                f"Our records show the loan status as "
                f"{customer['status']}."
            )

            date_message = (
                "The due date is currently unavailable "
                "in our records."
            )

        # -------------------------------------
        # Generate controlled message
        # -------------------------------------

        message = f"""
Subject: Loan Repayment Reminder

Dear {customer['name']},

I hope you are doing well.

{status_message}

The recorded outstanding loan amount is {formatted_amount}.

{date_message}

If you have already made a payment, kindly disregard this
reminder or contact us so that we can verify our records.

If you require clarification or wish to discuss available
repayment options, please contact the lender.

Thank you.

Best regards,
Customer Support Team
"""

        # -------------------------------------
        # Return communication result
        # -------------------------------------

        return {
            "customer_name": customer["name"],
            "customer_id": customer_id,
            "outstanding_amount": outstanding_amount,
            "loan_status": customer["status"],
            "message_draft": message.strip(),
            "approval_status": "Pending Human Approval"
        }


# =============================================
# MAIN PROGRAM
# =============================================

if __name__ == "__main__":

    agent = CommunicationAgent()

    print("\n======================================")
    print("       COMMUNICATION AGENT")
    print("======================================")

    # Customer ID input validation
    try:

        customer_id = int(
            input("\nEnter Customer ID (1-4): ")
        )

    except ValueError:

        print("Please enter a valid numeric Customer ID.")
        raise SystemExit

    # Generate communication draft
    try:

        print("\nGenerating repayment reminder...")

        result = agent.generate_message(customer_id)

        print("\n======================================")

        if isinstance(result, dict):

            print("CUSTOMER:", result["customer_name"])

            print(
                "OUTSTANDING AMOUNT: Rs.",
                result["outstanding_amount"]
            )

            print("LOAN STATUS:", result["loan_status"])

            print("\nMESSAGE DRAFT:")
            print("--------------------------------------")

            print(result["message_draft"])

            print("--------------------------------------")

            print("APPROVAL STATUS:", result["approval_status"])

        else:

            print(result)

        print("\n======================================")

    except Exception as error:

        print("\nApplication error:", repr(error))
