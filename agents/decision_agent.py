from datetime import date, datetime

from backend.database import get_connection


class DecisionAgent:

    def __init__(self):
        self.name = "Decision Making Agent"
        self.upcoming_reminder_days = 7

    def get_customer_data(self, customer_id):
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
                JOIN loans l ON c.customer_id = l.customer_id
                WHERE c.customer_id = ?
                ORDER BY l.loan_id
                LIMIT 1
            """, (customer_id,))
            result = cursor.fetchone()
            return dict(result) if result is not None else None
        finally:
            conn.close()

    def _decision_context(self, customer):
        """Fields that should be present in every decision response."""
        if customer is None:
            return {}
        return {
            "customer_id": customer.get("customer_id"),
            "customer_name": customer.get("name"),
            "loan_id": customer.get("loan_id"),
            "loan_status": customer.get("status"),
            "outstanding_amount": customer.get("outstanding_amount"),
            "due_date": customer.get("due_date"),
        }

    def make_decision(self, customer_id):
        customer = self.get_customer_data(customer_id)

        if customer is None:
            return {
                "customer_id": customer_id,
                "action": "manual_review",
                "priority": "High",
                "reason": "Customer or loan information not found.",
                "communication_required": False,
                "human_review_required": True,
            }

        context = self._decision_context(customer)
        today = date.today()
        loan_status = str(customer.get("status") or "").strip().lower()

        due_date = None
        try:
            if customer.get("due_date"):
                due_date = datetime.strptime(
                    str(customer["due_date"]), "%Y-%m-%d"
                ).date()
        except (ValueError, TypeError):
            due_date = None

        if loan_status == "overdue":
            return {
                **context,
                "action": "prepare_overdue_reminder",
                "priority": "High",
                "reason": "The database records the loan status as Overdue.",
                "communication_required": True,
                "human_review_required": True,
            }

        if loan_status in ["closed", "paid"]:
            return {
                **context,
                "action": "no_action_required",
                "priority": "Low",
                "reason": "The database records the loan status as Closed/Paid.",
                "communication_required": False,
                "human_review_required": False,
            }

        if loan_status == "active":
            if due_date is None:
                return {
                    **context,
                    "action": "manual_review",
                    "priority": "High",
                    "reason": (
                        "The loan is Active, but its due date is missing "
                        "or invalid. Verify the loan record."
                    ),
                    "communication_required": False,
                    "human_review_required": True,
                }

            days_remaining = (due_date - today).days

            if days_remaining < 0:
                return {
                    **context,
                    "action": "manual_review",
                    "priority": "High",
                    "reason": (
                        "The database records the loan as Active, but its "
                        "recorded due date has passed. Verify the loan status."
                    ),
                    "communication_required": False,
                    "human_review_required": True,
                    "days_since_due_date": abs(days_remaining),
                }

            if days_remaining <= self.upcoming_reminder_days:
                return {
                    **context,
                    "action": "prepare_upcoming_reminder",
                    "priority": "Medium",
                    "reason": (
                        f"The recorded due date is {days_remaining} days away."
                    ),
                    "communication_required": True,
                    "human_review_required": True,
                    "days_remaining": days_remaining,
                }

            return {
                **context,
                "action": "monitor_account",
                "priority": "Low",
                "reason": (
                    f"The recorded due date is {days_remaining} days away."
                ),
                "communication_required": False,
                "human_review_required": False,
                "days_remaining": days_remaining,
            }

        return {
            **context,
            "action": "manual_review",
            "priority": "High",
            "reason": (
                "The loan status is not recognised. "
                "Manual verification is required."
            ),
            "communication_required": False,
            "human_review_required": True,
        }


if __name__ == "__main__":
    agent = DecisionAgent()
    print("\n==============================================")
    print("          DECISION MAKING AGENT")
    print("==============================================")
    try:
        customer_id = int(input("\nEnter Customer ID (1-4): "))
        print("\nAnalysing customer account...")
        result = agent.make_decision(customer_id)
        print("\n==============================================")
        print("             DECISION RESULT")
        print("==============================================")
        for key, value in result.items():
            print(f"{key}: {value}")
        print("\n==============================================")
    except ValueError:
        print("\nEnter a valid numeric Customer ID.")
    except Exception as error:
        print("\nApplication error:", error)
