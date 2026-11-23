from backend.database import get_connection


# ==========================================
# RETRIEVE CUSTOMER INFORMATION
# ==========================================

def get_customer_data(customer_id):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                c.customer_id,
                c.name,
                c.monthly_income,
                c.employment_status,
                l.loan_id,
                l.loan_amount,
                l.outstanding_amount,
                l.due_date,
                l.interest_rate,
                l.status
            FROM customers c
            JOIN loans l ON c.customer_id = l.customer_id
            WHERE c.customer_id = ?
            ORDER BY l.loan_id
            LIMIT 1
        """, (customer_id,))

        customer = cursor.fetchone()
        if customer is None:
            return None

        cursor.execute("""
            SELECT amount, payment_date, status
            FROM payments
            WHERE loan_id = ?
            ORDER BY payment_date DESC
        """, (customer["loan_id"],))
        payments = cursor.fetchall()

        return {
            "customer": dict(customer),
            "payments": [dict(payment) for payment in payments],
        }
    finally:
        conn.close()


# ==========================================
# CUSTOMER ANALYSIS AGENT
# ==========================================

def analyze_customer(customer_id):
    data = get_customer_data(customer_id)
    if data is None:
        return "Customer not found in the database."

    customer = data["customer"]
    payments = data["payments"]

    successful_payments = [
        payment for payment in payments
        if str(payment["status"] or "").strip().lower() == "paid"
    ]
    failed_payments = [
        payment for payment in payments
        if str(payment["status"] or "").strip().lower() == "failed"
    ]

    total_paid = sum(
        float(payment["amount"] or 0)
        for payment in successful_payments
    )

    original_loan = float(customer["loan_amount"] or 0)
    outstanding = float(customer["outstanding_amount"] or 0)

    repayment_percentage = (
        (total_paid / original_loan) * 100 if original_loan > 0 else 0
    )
    outstanding_percentage = (
        (outstanding / original_loan) * 100 if original_loan > 0 else 0
    )

    report = []
    report.append("=" * 55)
    report.append("       CUSTOMER FINANCIAL ANALYSIS")
    report.append("=" * 55)

    report.append("\n1. CUSTOMER INFORMATION")
    report.append(f"Customer ID: {customer['customer_id']}")
    report.append(f"Customer Name: {customer['name']}")
    report.append(
        f"Monthly Income: Rs. {float(customer['monthly_income'] or 0):,.2f}"
    )
    report.append(f"Employment Status: {customer['employment_status']}")

    report.append("\n2. LOAN INFORMATION")
    report.append(f"Loan ID: {customer['loan_id']}")
    report.append(f"Original Loan Amount: Rs. {original_loan:,.2f}")
    report.append(f"Outstanding Amount: Rs. {outstanding:,.2f}")
    report.append(f"Interest Rate: {customer['interest_rate']}%")
    report.append(f"Due Date: {customer['due_date']}")
    report.append(
        f"Database-Recorded Loan Status: {customer['status']}"
    )

    report.append("\n3. REPAYMENT HISTORY")
    report.append(f"Total Payment Records: {len(payments)}")
    report.append(f"Successful Payments: {len(successful_payments)}")
    report.append(f"Failed Payments: {len(failed_payments)}")
    report.append(f"Total Amount Paid: Rs. {total_paid:,.2f}")
    report.append(f"Repayment Percentage: {repayment_percentage:.2f}%")
    report.append(f"Outstanding Percentage: {outstanding_percentage:.2f}%")

    if payments:
        report.append("\nIndividual Payment Records:")
        for payment in payments:
            report.append(
                f"- Date: {payment['payment_date']} | "
                f"Amount: Rs. {float(payment['amount'] or 0):,.2f} | "
                f"Status: {payment['status']}"
            )
    else:
        report.append(
            "No payment records are available in the database."
        )

    report.append("\n4. VERIFIED OBSERVATIONS")
    if str(customer["status"] or "").strip().lower() == "overdue":
        report.append(
            "- The loan is recorded as Overdue in the database."
        )
    else:
        report.append(
            f"- The loan is recorded with status: {customer['status']}."
        )

    report.append(
        f"- The recorded outstanding balance is Rs. {outstanding:,.2f}."
    )
    report.append(
        f"- Recorded successful payments total Rs. {total_paid:,.2f}."
    )
    report.append(
        "- Repayment and outstanding percentages are each calculated "
        "against the original loan amount; they are not a reconciliation."
    )
    report.append(
        f"- The repayment percentage of the original loan is "
        f"{repayment_percentage:.2f}%."
    )

    report.append("\n5. MISSING INFORMATION")
    report.append("- Monthly household expenses.")
    report.append("- Contractual EMI amount.")
    report.append("- Complete repayment schedule.")
    report.append("- Other outstanding financial obligations.")
    report.append("- Penalties or additional charges, if applicable.")

    loan_status = str(customer["status"] or "").strip().lower()
    if loan_status == "overdue":
        report.append("- Reason for the recorded overdue status.")
    else:
        report.append(
            "- Details of any adjustments, fees, or transactions "
            "affecting the recorded outstanding balance."
        )

    report.append("\n6. RECOMMENDED HUMAN REVIEW")
    report.append("- Verify the loan repayment schedule.")
    report.append(
        "- Review the outstanding balance against the lender's loan records."
    )
    report.append("- Confirm whether additional charges apply.")
    report.append(
        "- Discuss available repayment options with the customer, if appropriate."
    )
    report.append(
        "- Obtain human approval before taking any collection action."
    )

    report.append("\n" + "=" * 55)
    report.append("END OF CUSTOMER FINANCIAL ANALYSIS")
    report.append("=" * 55)

    return "\n".join(report)


if __name__ == "__main__":
    print("\nCUSTOMER ANALYSIS AGENT")
    try:
        customer_id = int(input("Enter Customer ID (1-4): "))
        print("\n")
        print(analyze_customer(customer_id))
    except ValueError:
        print("Please enter a valid numeric Customer ID.")
    except Exception as error:
        print(f"Application error: {error}")
