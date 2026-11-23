import streamlit as st
import requests
import pandas as pd
import os


# -----------------------------------
# PAGE CONFIGURATION
# -----------------------------------

st.set_page_config(
    page_title="AI Debt Management System",
    page_icon="🤖",
    layout="wide"
)

API_URL = os.getenv(
    "API_URL",
    "http://127.0.0.1:8001"
).rstrip("/")

# Read the API key from the environment first, then Streamlit secrets.
API_KEY = os.getenv("DEBT_API_KEY", "").strip()
if not API_KEY:
    try:
        API_KEY = str(st.secrets.get("DEBT_API_KEY", "")).strip()
    except Exception:
        API_KEY = ""


def api_headers():
    """Headers required by authenticated FastAPI endpoints."""
    if not API_KEY:
        st.error(
            "API key is missing. Set DEBT_API_KEY in the terminal "
            "used to start Streamlit, then restart the dashboard."
        )
        return {}
    return {"x-api-key": API_KEY}



# -----------------------------------
# CUSTOM STYLING
# -----------------------------------

st.markdown("""
<style>
    .main-title {
        font-size: 32px;
        font-weight: bold;
        color: #3B82F6;
    }

    .subtitle {
        font-size: 16px;
        color: #94A3B8;
    }

    div[data-testid="stMetric"] {
        background-color: #1E293B;
        padding: 20px;
        border-radius: 12px;
        border: 1px solid #334155;
    }

    div[data-testid="stMetricLabel"] {
        color: #CBD5E1 !important;
    }

    div[data-testid="stMetricValue"] {
        color: #FFFFFF !important;
    }
</style>
""", unsafe_allow_html=True)


# -----------------------------------
# API FUNCTIONS
# -----------------------------------

def get_customers():
    try:
        response = requests.get(
            f"{API_URL}/customers",
            headers=api_headers(),
            timeout=10
        )

        response.raise_for_status()
        return response.json()

    except requests.RequestException as error:
        st.error(f"Could not connect to backend: {error}")
        return []


def get_customer_details(customer_id):
    try:
        response = requests.get(
            f"{API_URL}/customers/{customer_id}",
            headers=api_headers(),
            timeout=10
        )

        response.raise_for_status()
        return response.json()

    except requests.RequestException as error:
        st.error(f"Could not retrieve customer details: {error}")
        return None


def run_ai_analysis(customer_id):
    try:
        with st.spinner(
            "AI agents are analyzing customer information..."
        ):
            response = requests.post(
                f"{API_URL}/analyze/{customer_id}",
                headers=api_headers(),
                timeout=300
            )

            response.raise_for_status()
            return response.json()

    except requests.RequestException as error:
        st.error(f"AI analysis failed: {error}")
        return None


def get_agent_logs(customer_id=None, limit=100):
    """Fetch persistent execution logs from the FastAPI backend."""
    try:
        params = {"limit": limit}
        if customer_id is not None:
            params["customer_id"] = customer_id

        response = requests.get(
            f"{API_URL}/agent-logs",
            params=params,
            headers=api_headers(),
            timeout=15
        )
        response.raise_for_status()
        return response.json()

    except requests.RequestException as error:
        st.error(f"Could not retrieve agent execution logs: {error}")
        return None




def get_pending_communications():
    """Fetch communication drafts waiting for human review."""
    try:
        response = requests.get(
            f"{API_URL}/communications/pending",
            headers=api_headers(),
            timeout=15
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as error:
        st.error(f"Could not retrieve pending communications: {error}")
        return None


def review_communication(approval_id, decision, reviewer_name, review_notes):
    """Submit an approval or rejection decision to the backend."""
    try:
        response = requests.post(
            f"{API_URL}/communications/{approval_id}/review",
            json={
                "decision": decision,
                "reviewer_name": reviewer_name,
                "review_notes": review_notes or None
            },
            headers=api_headers(),
            timeout=15
        )
        response.raise_for_status()
        return response.json()
    except requests.HTTPError as error:
        detail = error.response.text if error.response is not None else str(error)
        st.error(f"Could not submit review: {detail}")
    except requests.RequestException as error:
        st.error(f"Could not connect to the approval API: {error}")
    return None


def get_communication_history(customer_id=None, limit=100):
    """Fetch previously reviewed communication drafts."""
    try:
        params = {"limit": limit}
        if customer_id is not None:
            params["customer_id"] = customer_id
        response = requests.get(
            f"{API_URL}/communications/history",
            params=params,
            headers=api_headers(),
            timeout=15
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as error:
        st.error(f"Could not retrieve communication history: {error}")
        return None


def extract_history_records(history_response):
    """Support list responses and common dictionary-wrapped responses."""
    if isinstance(history_response, list):
        return history_response
    if isinstance(history_response, dict):
        for key in ("communications", "history", "records", "approvals"):
            value = history_response.get(key)
            if isinstance(value, list):
                return value
    return []

# -----------------------------------
# HEADER
# -----------------------------------

st.markdown(
    '<p class="main-title">🤖 Autonomous AI Debt Management</p>',
    unsafe_allow_html=True
)

st.markdown(
    '<p class="subtitle">AI-powered customer analysis, payment tracking and debt management</p>',
    unsafe_allow_html=True
)

st.divider()


# -----------------------------------
# BACKEND CONNECTION
# -----------------------------------

try:
    health = requests.get(
        f"{API_URL}/health",
        timeout=5
    )

    if health.status_code == 200:
        st.success("Backend connected successfully")
    else:
        st.warning("Backend is responding with an issue")

except requests.RequestException:
    st.error(
        "Backend is not running. Start FastAPI before using the dashboard."
    )
    st.stop()


# -----------------------------------
# LOAD CUSTOMER DATA
# -----------------------------------

customers = get_customers()

if not customers:
    st.warning("No customer records found.")
    st.stop()

df = pd.DataFrame(customers)


# -----------------------------------
# SIDEBAR NAVIGATION
# -----------------------------------

st.sidebar.title("Navigation")

page = st.sidebar.radio(
    "Select a page",
    [
        "Dashboard",
        "Customer Management",
        "AI Analysis",
        "Communication Approvals",
        "Agent Execution Logs"
    ]
)


# ===================================
# PAGE 1: DASHBOARD
# ===================================

if page == "Dashboard":

    st.header("Dashboard Overview")

    total_customers = len(df)

    total_outstanding = (
        df["outstanding_amount"].fillna(0).sum()
    )

    overdue_loans = (
        df["loan_status"] == "Overdue"
    ).sum()

    total_loans = df["loan_id"].notna().sum()

    # Dashboard metrics

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Total Customers",
        total_customers
    )

    col2.metric(
        "Total Loans",
        total_loans
    )

    col3.metric(
        "Outstanding Debt",
        f"₹{total_outstanding:,.0f}"
    )

    col4.metric(
        "Overdue Loans",
        int(overdue_loans)
    )

    st.divider()

    # Customer loan overview

    st.subheader("Customer Loan Overview")

    display_df = df[
        [
            "customer_id",
            "name",
            "monthly_income",
            "loan_amount",
            "outstanding_amount",
            "loan_status"
        ]
    ].copy()

    display_df.columns = [
        "Customer ID",
        "Customer Name",
        "Monthly Income (₹)",
        "Loan Amount (₹)",
        "Outstanding Amount (₹)",
        "Loan Status"
    ]

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True
    )

    st.divider()

    # Outstanding debt chart

    st.subheader("Outstanding Amount by Customer")

    chart_df = df[
        ["name", "outstanding_amount"]
    ].dropna().set_index("name")

    st.bar_chart(
        chart_df,
        horizontal=True,
        height=350
    )


# ===================================
# PAGE 2: CUSTOMER MANAGEMENT
# ===================================

elif page == "Customer Management":

    st.header("Customer Management")

    customer_options = {
        f"{row['name']} (ID: {row['customer_id']})":
        row["customer_id"]
        for _, row in df.iterrows()
    }

    selected_customer = st.selectbox(
        "Select Customer",
        list(customer_options.keys())
    )

    customer_id = customer_options[selected_customer]

    details = get_customer_details(customer_id)

    if details:

        customer = details["customer"]

        st.subheader(customer["name"])

        col1, col2, col3 = st.columns(3)

        col1.metric(
            "Customer ID",
            customer["customer_id"]
        )

        col2.metric(
            "Monthly Income",
            f"₹{customer['monthly_income']:,.0f}"
        )

        col3.metric(
            "Employment",
            customer["employment_status"]
        )

        st.write("**Email:**", customer["email"])
        st.write("**Phone:**", customer["phone"])

        st.divider()

        st.subheader("Loan Information")

        loans = details["loans"]

        if loans:

            for loan in loans:

                with st.expander(
                    f"Loan ID: {loan['loan_id']}"
                ):

                    col1, col2, col3 = st.columns(3)

                    col1.metric(
                        "Original Loan",
                        f"₹{loan['loan_amount']:,.0f}"
                    )

                    col2.metric(
                        "Outstanding",
                        f"₹{loan['outstanding_amount']:,.0f}"
                    )

                    col3.metric(
                        "Interest Rate",
                        f"{loan['interest_rate']}%"
                    )

                    st.write(
                        "**Due Date:**",
                        loan["due_date"]
                    )

                    st.write(
                        "**Status:**",
                        loan["status"]
                    )

                    st.subheader("Payment Records")

                    payments = loan["payments"]

                    if payments:

                        payment_df = pd.DataFrame(payments)

                        st.dataframe(
                            payment_df,
                            use_container_width=True,
                            hide_index=True
                        )

                    else:
                        st.info("No payment records available.")

        else:
            st.info("No loans found for this customer.")


# ===================================
# PAGE 3: AI ANALYSIS
# ===================================

elif page == "AI Analysis":

    st.header("Autonomous AI Analysis")

    st.write(
        "Select a customer to execute the multi-agent "
        "debt management workflow."
    )

    customer_options = {
        f"{row['name']} (ID: {row['customer_id']})":
        row["customer_id"]
        for _, row in df.iterrows()
    }

    selected_customer = st.selectbox(
        "Choose Customer",
        list(customer_options.keys())
    )

    customer_id = customer_options[selected_customer]

    if st.button(
        "🚀 Run AI Analysis",
        use_container_width=True
    ):

        result = run_ai_analysis(customer_id)

        if result:
            st.session_state["analysis_result"] = result

    result = st.session_state.get("analysis_result")

    if result and result.get("customer_id") == customer_id:

        st.divider()

        st.success(
            f"Analysis status: {result.get('status', 'Completed')}"
        )

        # -----------------------------------
        # 1. CUSTOMER ANALYSIS AGENT
        # -----------------------------------

        st.subheader("1. Customer Analysis Agent")

        with st.expander(
            "View Customer Analysis",
            expanded=True
        ):

            st.write(
                result.get("customer_analysis")
                or "No customer analysis available."
            )

        # -----------------------------------
        # 2. PAYMENT HISTORY AGENT
        # -----------------------------------

        st.subheader("2. Payment History Agent")

        payment_data = result.get("payment_analysis")

        if payment_data:

            metrics = payment_data.get(
                "financial_metrics",
                {}
            )

            col1, col2, col3 = st.columns(3)

            col1.metric(
                "Total Paid",
                f"₹{metrics.get('total_paid', 0):,.0f}"
            )

            col2.metric(
                "Outstanding",
                f"₹{metrics.get('outstanding', metrics.get('outstanding_amount', 0)):,.0f}"
            )

            col3.metric(
                "Repayment",
                f"{metrics.get('repayment_percentage', 0)}%"
            )

            st.divider()

            st.subheader("Payment Summary")

            summary_col1, summary_col2, summary_col3 = st.columns(3)

            summary_col1.metric(
                "Successful Payments",
                metrics.get("successful_payments", 0)
            )

            summary_col2.metric(
                "Failed Payments",
                metrics.get("failed_payments", 0)
            )

            summary_col3.metric(
                "Total Payment Records",
                metrics.get("total_records", 0)
            )

            st.write(
                "**Original Loan Amount:**",
                f"₹{metrics.get('original_loan', 0):,.0f}"
            )

            st.write(
                "**Loan Status:**",
                metrics.get("loan_status", "Not available")
            )

            st.write(
                "**Due Date:**",
                metrics.get("due_date", "Not available")
            )

            with st.expander("Full Payment Analysis"):
                st.json(payment_data)

        else:

            st.warning(
                "Payment analysis is not available for this customer."
            )

        # -----------------------------------
        # 3. DATA VALIDATION AGENT
        # -----------------------------------

        st.subheader("3. Data Validation Agent")

        validation = result.get("data_validation")

        if validation:

            validation_status = validation.get(
                "validation_status", "UNKNOWN"
            ).upper()

            if validation_status == "PASSED":
                st.success("Data validation PASSED. No issues detected.")
            elif validation_status == "WARNING":
                st.warning(
                    "Data validation WARNING. Human verification is required."
                )
            elif validation_status == "FAILED":
                st.error(
                    "Data validation FAILED. Do not rely on these records "
                    "until they have been reviewed."
                )
            else:
                st.info(f"Validation status: {validation_status}")

            validation_col1, validation_col2, validation_col3, validation_col4 = st.columns(4)

            validation_col1.metric(
                "Loans Checked",
                validation.get("total_loans_checked", 0)
            )

            validation_col2.metric(
                "Total Issues",
                validation.get("total_issues", 0)
            )

            validation_col3.metric(
                "Errors",
                validation.get("error_count", 0)
            )

            validation_col4.metric(
                "Warnings",
                validation.get("warning_count", 0)
            )

            issues = validation.get("issues", [])

            if issues:
                st.markdown("#### Validation Issues")

                for index, issue in enumerate(issues, start=1):
                    severity = issue.get("severity", "UNKNOWN").upper()
                    code = issue.get("code", "unspecified_issue")
                    message = issue.get("message", "No issue description provided.")
                    loan_id = issue.get("loan_id")

                    title = f"{index}. {severity}: {code}"
                    if loan_id is not None:
                        title += f" (Loan ID: {loan_id})"

                    if severity == "ERROR":
                        st.error(f"**{title}**\n\n{message}")
                    elif severity == "WARNING":
                        st.warning(f"**{title}**\n\n{message}")
                    else:
                        st.info(f"**{title}**\n\n{message}")
            else:
                st.info("No validation issues were reported.")

            with st.expander("Full Data Validation Output"):
                st.json(validation)

        else:
            st.warning(
                "Data validation output is missing. Treat the records as "
                "unverified and investigate the workflow response."
            )

        # -----------------------------------
        # 4. DECISION AGENT
        # -----------------------------------

        st.subheader("3. Decision Agent")

        decision = result.get("decision")

        if decision:

            action = decision.get(
                "action",
                "Not available"
            )

            priority = decision.get(
                "priority",
                "Not available"
            )

            reason = decision.get(
                "reason",
                "No reason provided."
            )

            st.markdown("### Recommended Action")

            decision_col1, decision_col2 = st.columns(2)

            decision_col1.metric(
                "Action",
                action.replace("_", " ").title()
            )

            decision_col2.metric(
                "Priority",
                priority
            )

            st.info(f"**Reason:** {reason}")

            st.markdown("### Decision Details")

            detail_col1, detail_col2 = st.columns(2)

            communication_required = decision.get(
                "communication_required",
                False
            )

            human_review_required = decision.get(
                "human_review_required",
                False
            )

            detail_col1.write(
                "**Communication Required:**"
            )

            if communication_required:
                detail_col1.warning("Yes")
            else:
                detail_col1.success("No")

            detail_col2.write(
                "**Human Review Required:**"
            )

            if human_review_required:
                detail_col2.warning("Yes")
            else:
                detail_col2.success("No")

            st.markdown("### Loan Details")

            loan_col1, loan_col2, loan_col3 = st.columns(3)

            loan_col1.metric(
                "Loan Status",
                decision.get("loan_status", "Not available")
            )

            loan_col2.metric(
                "Outstanding Amount",
                f"₹{decision.get('outstanding_amount', 0):,.0f}"
                if decision.get("outstanding_amount") is not None
                else "Not available"
            )

            loan_col3.metric(
                "Due Date",
                decision.get("due_date", "Not available")
            )

            if decision.get("days_remaining") is not None:
                st.write(
                    f"**Days Remaining:** {decision['days_remaining']}"
                )

            with st.expander("Full Decision Agent Output"):
                st.json(decision)

        else:

            st.warning(
                "Decision Agent output is not available."
            )

        # -----------------------------------
        # 5. COMMUNICATION AGENT
        # -----------------------------------

        st.subheader("4. Communication Agent")

        communication = result.get("communication_draft")

        if communication:

            st.info(
                "Human approval required before using this message."
            )

            st.write(
                "**Customer:**",
                communication.get("customer_name")
            )

            st.write(
                "**Approval Status:**",
                communication.get("approval_status")
            )

            st.text_area(
                "Communication Draft",
                value=communication.get("message_draft", ""),
                height=180
            )

        elif decision and not decision.get(
            "communication_required",
            False
        ):

            validation_status = (result.get("data_validation") or {}).get(
                "validation_status", "UNKNOWN"
            ).upper()

            if validation_status != "PASSED":
                st.warning(
                    "Communication Agent was skipped because data validation "
                    f"status is {validation_status}. Human review is required "
                    "before any communication can be prepared."
                )
            else:
                st.success(
                    "Communication Agent was skipped because "
                    "the Decision Agent determined that no "
                    "communication is currently required."
                )

        else:

            st.warning(
                "Communication draft is unavailable. "
                "Check the workflow errors."
            )

        # -----------------------------------
        # 6. REPORT GENERATION AGENT
        # -----------------------------------

        st.subheader("5. Report Generation Agent")

        report = result.get("final_report")

        if report:

            with st.expander(
                "View Final AI Report",
                expanded=True
            ):

                st.json(report)

        else:

            st.warning(
                "Final report is not available."
            )

        # -----------------------------------
        # WORKFLOW ERRORS
        # -----------------------------------

        errors = result.get("errors", [])

        if errors:

            st.warning(
                "Some workflow steps reported errors."
            )

            for error in errors:
                st.write(error)

        else:

            st.success(
                "All workflow steps completed successfully."
            )




# ===================================
# PAGE 4: COMMUNICATION APPROVALS
# ===================================

elif page == "Communication Approvals":

    st.header("Human-in-the-Loop Communication Review")
    st.write(
        "Review communication drafts generated by the AI workflow. "
        "Approving or rejecting a draft records the decision; it does not "
        "send a message to the customer."
    )
    st.info(
        "Verify the customer and loan details before making a decision. "
        "This dashboard records the review only; it does not send messages."
    )

    pending_response = get_pending_communications()

    if pending_response is not None:
        if isinstance(pending_response, dict):
            pending_items = pending_response.get("communications", [])
            total_pending = pending_response.get("total_pending", len(pending_items))
        elif isinstance(pending_response, list):
            pending_items = pending_response
            total_pending = len(pending_items)
        else:
            pending_items = []
            total_pending = 0

        st.metric("Drafts Awaiting Review", total_pending)

        if pending_items:
            for item in pending_items:
                approval_id = item.get("approval_id")
                customer_name = item.get("customer_name", "Unknown customer")
                customer_id = item.get("customer_id", "N/A")
                loan_id = item.get("loan_id", "N/A")
                status = item.get("approval_status", "Unknown")

                with st.expander(
                    f"Approval #{approval_id} | {customer_name} | {status}",
                    expanded=True
                ):
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Approval ID", approval_id or "N/A")
                    col2.metric("Customer ID", customer_id)
                    col3.metric("Loan ID", loan_id or "N/A")

                    st.write(f"**Customer:** {customer_name}")
                    if item.get("customer_email"):
                        st.write(f"**Email:** {item['customer_email']}")
                    st.write(f"**Created:** {item.get('created_at', 'N/A')}")

                    st.text_area(
                        "Communication Draft",
                        value=item.get("message_draft", ""),
                        height=220,
                        key=f"approval_message_{approval_id}",
                        disabled=True
                    )

                    reviewer_name = st.text_input(
                        "Reviewer name",
                        key=f"reviewer_name_{approval_id}",
                        placeholder="Enter your name"
                    )
                    review_notes = st.text_area(
                        "Review notes (optional)",
                        key=f"review_notes_{approval_id}",
                        height=80
                    )

                    approve_col, reject_col = st.columns(2)
                    approve_clicked = approve_col.button(
                        "Approve Draft",
                        key=f"approve_{approval_id}",
                        type="primary",
                        use_container_width=True
                    )
                    reject_clicked = reject_col.button(
                        "Reject Draft",
                        key=f"reject_{approval_id}",
                        use_container_width=True
                    )

                    if approve_clicked or reject_clicked:
                        if len(reviewer_name.strip()) < 2:
                            st.error("Enter a reviewer name (at least 2 characters).")
                        else:
                            decision_value = "approve" if approve_clicked else "reject"
                            review_result = review_communication(
                                approval_id,
                                decision_value,
                                reviewer_name.strip(),
                                review_notes.strip()
                            )
                            if review_result:
                                st.success(review_result.get(
                                    "message", "Review submitted successfully."
                                ))
                                st.info(
                                    "The review decision was recorded. "
                                    "No communication was sent."
                                )
                                st.rerun()
        else:
            st.success("There are no communications waiting for approval.")

    st.divider()
    st.subheader("Communication Approval History")

    history_filter_col, history_limit_col = st.columns([2, 1])
    history_customer_options = {"All Customers": None}
    for _, row in df.iterrows():
        history_customer_options[
            f"{row['name']} (ID: {row['customer_id']})"
        ] = int(row["customer_id"])

    selected_history_filter = history_filter_col.selectbox(
        "Filter by customer",
        list(history_customer_options.keys()),
        key="approval_history_customer_filter"
    )
    selected_history_customer_id = history_customer_options[selected_history_filter]

    history_limit = history_limit_col.selectbox(
        "Maximum records",
        [25, 50, 100, 250, 500],
        index=2,
        key="approval_history_limit"
    )

    history_response = get_communication_history(
        customer_id=selected_history_customer_id,
        limit=history_limit
    )

    if history_response is not None:
        history_records = extract_history_records(history_response)
        if history_records:
            history_df = pd.DataFrame(history_records)
            st.dataframe(history_df, use_container_width=True, hide_index=True)
            with st.expander("View full approval history records"):
                st.json(history_records)
        else:
            st.info("No communication approval history was found.")


# ===================================
# PAGE 5: AGENT EXECUTION LOGS
# ===================================

elif page == "Agent Execution Logs":

    import json

    st.header("Agent Execution Logs")
    st.write(
        "Review the persistent execution history recorded by the "
        "multi-agent workflow."
    )

    filter_col, limit_col = st.columns([2, 1])

    customer_filter_options = {
        "All Customers": None
    }
    for _, row in df.iterrows():
        customer_filter_options[
            f"{row['name']} (ID: {row['customer_id']})"
        ] = int(row["customer_id"])

    selected_filter = filter_col.selectbox(
        "Filter by customer",
        list(customer_filter_options.keys())
    )
    selected_log_customer_id = customer_filter_options[selected_filter]

    log_limit = limit_col.selectbox(
        "Maximum records",
        [25, 50, 100, 250, 500],
        index=2
    )

    if st.button("🔄 Refresh Logs", use_container_width=True):
        st.session_state["refresh_agent_logs"] = True

    log_response = get_agent_logs(
        customer_id=selected_log_customer_id,
        limit=log_limit
    )

    if log_response is not None:
        logs = log_response.get("logs", [])

        if logs:
            logs_df = pd.DataFrame(logs)

            # Summary metrics
            total_logs = len(logs)
            success_count = sum(
                1 for item in logs
                if str(item.get("action", "")).upper() in {
                    "SUCCESS", "COMPLETED", "COMPLETED_MANUAL_REVIEW"
                }
            )
            warning_count = sum(
                1 for item in logs
                if "WARNING" in str(item.get("action", "")).upper()
            )
            failed_count = sum(
                1 for item in logs
                if "FAIL" in str(item.get("action", "")).upper()
                or "ERROR" in str(item.get("action", "")).upper()
            )

            metric1, metric2, metric3, metric4 = st.columns(4)
            metric1.metric("Log Records", total_logs)
            metric2.metric("Successful / Completed", success_count)
            metric3.metric("Warnings", warning_count)
            metric4.metric("Failures", failed_count)

            st.divider()
            st.subheader("Execution History")

            display_logs = logs_df.copy()
            if "result" in display_logs.columns:
                display_logs["result"] = display_logs["result"].apply(
                    lambda value: (
                        str(value)[:180] + "..."
                        if value is not None and len(str(value)) > 180
                        else value
                    )
                )

            preferred_columns = [
                column for column in [
                    "log_id", "customer_id", "agent_name",
                    "action", "created_at", "result"
                ] if column in display_logs.columns
            ]
            display_logs = display_logs[preferred_columns]
            display_logs = display_logs.rename(columns={
                "log_id": "Log ID",
                "customer_id": "Customer ID",
                "agent_name": "Agent",
                "action": "Status",
                "created_at": "Timestamp",
                "result": "Result Preview"
            })

            st.dataframe(
                display_logs,
                use_container_width=True,
                hide_index=True
            )

            st.divider()
            st.subheader("Detailed Log Records")

            for log in logs:
                title = (
                    f"Log #{log.get('log_id', 'N/A')} | "
                    f"{log.get('agent_name', 'Unknown Agent')} | "
                    f"{log.get('action', 'Unknown Status')}"
                )

                with st.expander(title):
                    detail_col1, detail_col2 = st.columns(2)
                    detail_col1.write(
                        f"**Customer ID:** {log.get('customer_id', 'N/A')}"
                    )
                    detail_col2.write(
                        f"**Timestamp:** {log.get('created_at', 'N/A')}"
                    )

                    raw_result = log.get("result")
                    if isinstance(raw_result, str):
                        try:
                            parsed_result = json.loads(raw_result)
                            st.json(parsed_result)
                        except (json.JSONDecodeError, TypeError):
                            st.text(raw_result)
                    elif raw_result is not None:
                        st.json(raw_result)
                    else:
                        st.info("No result payload was stored for this log.")

            csv_data = logs_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "⬇️ Download Logs as CSV",
                data=csv_data,
                file_name="agent_execution_logs.csv",
                mime="text/csv",
                use_container_width=True
            )

        else:
            st.info("No agent execution logs were found for this filter.")


# -----------------------------------
# FOOTER
# -----------------------------------

st.divider()

st.caption(
    "Autonomous AI Debt Management System | "
    "Powered by Python, FastAPI, LangGraph, Ollama and Streamlit"
)