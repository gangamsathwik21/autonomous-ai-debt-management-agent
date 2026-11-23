import os

from langchain_ollama import ChatOllama

from backend.database import get_connection
from agents.data_validation import DataValidationAgent


class ReportGenerationAgent:

    def __init__(self):

        self.name = "Report Generation Agent"

        self.llm = ChatOllama(
            model="qwen2.5:3b",
            temperature=0,
            base_url=os.getenv(
                "OLLAMA_BASE_URL",
                "http://localhost:11434"
            )
        )

        self.validation_agent = DataValidationAgent()

    # =====================================================
    # 1. RETRIEVE CUSTOMER AND LOAN INFORMATION
    # =====================================================

    def get_customer_data(self, customer_id):

        conn = get_connection()

        try:

            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT
                    c.customer_id,
                    c.name,
                    c.email,
                    c.monthly_income,
                    c.employment_status,
                    l.loan_id,
                    l.loan_amount,
                    l.outstanding_amount,
                    l.interest_rate,
                    l.due_date,
                    l.status

                FROM customers c

                JOIN loans l
                ON c.customer_id = l.customer_id

                WHERE c.customer_id = ?

                ORDER BY l.loan_id ASC

                LIMIT 1
                """,
                (customer_id,)
            )

            loan = cursor.fetchone()

            if loan is None:
                return None

            cursor.execute(
                """
                SELECT
                    payment_id,
                    amount,
                    payment_date,
                    status

                FROM payments

                WHERE loan_id = ?

                ORDER BY payment_date ASC, payment_id ASC
                """,
                (loan["loan_id"],)
            )

            payments = cursor.fetchall()

            return {
                "customer": dict(loan),
                "payments": [
                    dict(payment)
                    for payment in payments
                ]
            }

        finally:

            conn.close()

    # =====================================================
    # 2. CALCULATE FINANCIAL METRICS
    # =====================================================

    def calculate_metrics(self, data):

        customer = data["customer"]
        payments = data["payments"]

        successful_payments = [
            payment
            for payment in payments
            if str(payment["status"]).strip().lower() == "paid"
        ]

        failed_payments = [
            payment
            for payment in payments
            if str(payment["status"]).strip().lower() == "failed"
        ]

        total_paid = sum(
            float(payment["amount"] or 0)
            for payment in successful_payments
        )

        original_loan = float(
            customer["loan_amount"] or 0
        )

        outstanding = float(
            customer["outstanding_amount"] or 0
        )

        repayment_percentage = (
            (total_paid / original_loan) * 100
            if original_loan > 0
            else 0
        )

        outstanding_percentage = (
            (outstanding / original_loan) * 100
            if original_loan > 0
            else 0
        )

        return {

            "total_paid": round(total_paid, 2),

            "outstanding": round(outstanding, 2),

            "successful_payments": len(
                successful_payments
            ),

            "failed_payments": len(
                failed_payments
            ),

            "total_records": len(payments),

            "repayment_percentage": round(
                repayment_percentage,
                2
            ),

            "outstanding_percentage": round(
                outstanding_percentage,
                2
            )
        }

    # =====================================================
    # 3. PREPARE FINANCIAL FACTS
    # =====================================================

    def prepare_financial_facts(self, data, metrics):

        customer = data["customer"]
        payments = data["payments"]

        if payments:

            payment_details = []

            for payment in payments:

                payment_details.append(
                    f"""
Payment ID: {payment['payment_id']}
Amount: Rs. {payment['amount']}
Payment Date: {payment['payment_date']}
Payment Status: {payment['status']}
"""
                )

            payment_details = "\n".join(
                payment_details
            )

        else:

            payment_details = "No payment records available."

        facts = f"""

CUSTOMER INFORMATION

Customer ID: {customer['customer_id']}
Name: {customer['name']}
Email: {customer['email']}
Monthly Income: Rs. {customer['monthly_income']}
Employment Status: {customer['employment_status']}


LOAN INFORMATION

Loan ID: {customer['loan_id']}
Original Loan Amount: Rs. {customer['loan_amount']}
Recorded Outstanding Amount: Rs. {customer['outstanding_amount']}
Interest Rate: {customer['interest_rate']}%
Due Date: {customer['due_date']}
Database-Recorded Loan Status: {customer['status']}


REPAYMENT METRICS

Total Amount Paid in Recorded Successful Payments:
Rs. {metrics['total_paid']}

Successful Payments:
{metrics['successful_payments']}

Failed Payments:
{metrics['failed_payments']}

Total Payment Records:
{metrics['total_records']}

Repayment Percentage of Original Loan:
{metrics['repayment_percentage']}%

Outstanding Percentage of Original Loan:
{metrics['outstanding_percentage']}%


INDIVIDUAL PAYMENT RECORDS

{payment_details}


IMPORTANT DATA LIMITATIONS

The payment records represent only the transactions
available in the database.

They may not represent the customer's complete
repayment history.

Do not assume that missing transactions mean
that payments were not made.

The recorded outstanding balance is taken directly
from the database.

The outstanding balance may include adjustments,
interest, fees or other amounts not represented
in the available payment records.

Do not assume that the difference between the
original loan amount and recorded outstanding
balance is caused only by recorded payments.

"""

        return facts

    # =====================================================
    # 4. FORMAT VALIDATION ISSUES
    # =====================================================

    def _issue_to_text(self, issue):

        if isinstance(issue, dict):

            severity = issue.get(
                "severity",
                "UNKNOWN"
            )

            code = issue.get(
                "code",
                "unspecified"
            )

            message = issue.get(
                "message",
                "No description available."
            )

            loan_id = issue.get("loan_id")

            result = (
                f"- {severity}: {message} "
                f"(Code: {code})"
            )

            if loan_id is not None:

                result += f" (Loan ID: {loan_id})"

            return result

        return f"- {str(issue)}"

    # =====================================================
    # 5. PREPARE VALIDATION SUMMARY
    # =====================================================

    def prepare_validation_summary(self, validation):

        if not isinstance(validation, dict):

            return {
                "validation_status": "UNAVAILABLE",
                "error_count": 0,
                "warning_count": 0,
                "issues": [],
                "summary": "Data validation results are unavailable."
            }

        status = validation.get(
            "validation_status",
            "UNAVAILABLE"
        )

        error_count = validation.get(
            "error_count",
            0
        )

        warning_count = validation.get(
            "warning_count",
            0
        )

        issues = validation.get(
            "issues",
            []
        )

        if issues:

            issue_text = "\n".join(
                self._issue_to_text(issue)
                for issue in issues
            )

        else:

            issue_text = "No validation issues were identified."

        summary = f"""
DATA VALIDATION SUMMARY

Validation Status: {status}

Errors: {error_count}

Warnings: {warning_count}

Validation Issues:

{issue_text}
"""

        return {

            "validation_status": status,

            "error_count": error_count,

            "warning_count": warning_count,

            "issues": issues,

            "summary": summary
        }

    # =====================================================
    # 6. GENERATE AI FINANCIAL ANALYSIS
    # =====================================================

    def generate_ai_analysis(self, facts):

        prompt = f"""

You are a professional financial reporting assistant
working in an AI-powered debt management system.

Generate a clear, concise and factual financial report
using ONLY the supplied information.

SOURCE DATA:

{facts}


STRICT RULES
============

1. Never invent financial information.

2. Never invent customer details, loan amounts,
   outstanding balances, dates or payment transactions.

3. Never assume that available payment records
   represent the customer's complete repayment history.

4. Never claim that the customer has or has not made
   payments outside the records provided.

5. Never infer financial behaviour from missing records.

6. Never assume that the customer can afford repayment.

7. Never assess repayment ability using monthly income alone.

8. Never invent EMI amounts, household expenses,
   penalties or additional debts.

9. Treat loan status as the status recorded in the database.

10. Distinguish the original loan amount from the
    recorded outstanding amount.

11. Use the supplied calculated financial metrics.
    Do not independently recalculate them.

12. Do not assume that the outstanding balance is
    explained entirely by recorded payments.

13. If no payment records are available, explicitly
    state that no payment records are available.

14. Do not claim that missing payment records mean
    that the customer made no payments.

15. Do not make binding financial or legal decisions.


REPORT STRUCTURE
================

1. CUSTOMER OVERVIEW

Summarise the recorded customer information.

2. LOAN ASSESSMENT

Present the original loan amount, recorded outstanding
amount, interest rate, due date and database-recorded
loan status.

3. REPAYMENT HISTORY

Present successful payments, failed payments,
total payment records, total recorded amount paid,
repayment percentage and outstanding percentage.

4. FINANCIAL OBSERVATIONS

Include only observations directly supported
by the supplied records.

5. DATA VALIDATION RESULTS

Explain the actual validation status,
errors, warnings and issues.

6. MISSING INFORMATION

Identify information unavailable in the database.

7. SUGGESTED NEXT STEPS

Recommend appropriate record verification,
human review and responsible account monitoring.


WRITING REQUIREMENTS
====================

- Use professional language.
- Use neutral and respectful wording.
- Avoid unsupported conclusions.
- Avoid unnecessary repetition.
- Do not make assumptions about personal circumstances.
- Do not make collection decisions.

Return only the financial report.

"""

        response = self.llm.invoke(prompt)

        if not hasattr(response, "content"):

            raise ValueError(
                "The language model returned an invalid response."
            )

        if not isinstance(response.content, str):

            raise ValueError(
                "The language model returned non-text content."
            )

        result = response.content.strip()

        if not result:

            raise ValueError(
                "The language model returned an empty report."
            )

        return result

    # =====================================================
    # 7. GENERATE CONSOLIDATED REPORT
    # =====================================================

    def generate_report(
        self,
        customer_id,
        communication_draft=None
    ):

        # Retrieve customer information

        data = self.get_customer_data(customer_id)

        if data is None:
            return None

        customer = data["customer"]

        # Calculate deterministic metrics

        metrics = self.calculate_metrics(data)

        # Prepare financial facts

        facts = self.prepare_financial_facts(
            data,
            metrics
        )

        # Perform data validation

        try:

            validation = self.validation_agent.validate_customer(
                customer_id
            )

            if not isinstance(validation, dict):

                raise ValueError(
                    "Invalid data validation result."
                )

        except Exception as error:

            print(
                "[VALIDATION ERROR]",
                type(error).__name__,
                str(error)
            )

            validation = {

                "customer_id": customer_id,

                "validation_status": "FAILED",

                "error_count": 1,

                "warning_count": 0,

                "issues": [
                    {
                        "severity": "ERROR",
                        "code": "validation_agent_failure",
                        "message": (
                            "Data validation could not be completed. "
                            "Manual review is required."
                        )
                    }
                ]
            }

        validation_summary = (
            self.prepare_validation_summary(validation)
        )

        # Include validation information in AI source facts

        complete_facts = (
            facts
            + "\n\n"
            + validation_summary["summary"]
        )

        # Generate AI analysis

        try:

            analysis = self.generate_ai_analysis(
                complete_facts
            )

        except Exception as error:

            print(
                "[REPORT GENERATION ERROR]",
                type(error).__name__,
                str(error)
            )

            error_text = str(error).lower()

            if (
                "ollama" in error_text
                or "connection" in error_text
            ):

                analysis = (
                    "AI analysis could not be generated. "
                    "Ollama unavailable. "
                    "Please review the deterministic financial "
                    "metrics and data validation results. "
                    "Human verification is required."
                )

            else:

                analysis = (
                    "AI analysis could not be generated. "
                    "Please review the deterministic financial "
                    "metrics and data validation results. "
                    "Human verification is required."
                )

        # Use the communication draft supplied by the workflow.
        # Do not generate a new draft here.

        report = {

            "customer_name": customer["name"],

            "customer_id": customer_id,

            "financial_metrics": metrics,

            "data_validation": validation,

            "validation_summary": validation_summary,

            "analysis": analysis,

            "communication_draft": communication_draft

        }

        return report


# =====================================================
# MAIN PROGRAM
# =====================================================

if __name__ == "__main__":

    agent = ReportGenerationAgent()

    print("\n==============================================")
    print("          REPORT GENERATION AGENT")
    print("==============================================")

    try:

        customer_id = int(
            input("\nEnter Customer ID (1-4): ")
        )

        report = agent.generate_report(customer_id)

        if report is None:

            print("\nCustomer not found.")

        else:

            print("\n==============================================")
            print("             FINANCIAL REPORT")
            print("==============================================")

            print(
                "\nCustomer:",
                report["customer_name"]
            )

            print(
                "Customer ID:",
                report["customer_id"]
            )

            print("\nFINANCIAL METRICS")

            print("----------------------------------------------")

            print(
                report["financial_metrics"]
            )

            print("\nDATA VALIDATION")

            print("----------------------------------------------")

            print(
                report["validation_summary"]["summary"]
            )

            print("\nAI FINANCIAL ANALYSIS")

            print("----------------------------------------------")

            print(
                report["analysis"]
            )

            print("\nCOMMUNICATION DRAFT")

            print("----------------------------------------------")

            print(
                report["communication_draft"]
            )

    except ValueError:

        print("\nInvalid customer ID. Please enter a number.")

    except Exception as error:

        print(
            "\nReport generation failed:",
            type(error).__name__,
            str(error)
        )