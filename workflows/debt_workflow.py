from typing import TypedDict, Any, Annotated
import operator

from langgraph.graph import StateGraph, START, END

from agents.customer_analysis import analyze_customer
from agents.payment_history import PaymentHistoryAgent
from agents.data_validation import DataValidationAgent
from agents.communication import CommunicationAgent
from agents.report_generation import ReportGenerationAgent
from agents.decision_agent import DecisionAgent
from backend.database import log_agent_execution


# =============================================
# 1. DEFINE WORKFLOW STATE
# =============================================

class DebtManagementState(TypedDict, total=False):

    customer_id: int

    customer_analysis: Any

    payment_analysis: Any

    data_validation: Any

    decision: Any

    communication_draft: Any

    final_report: Any

    errors: Annotated[list[str], operator.add]


# =============================================
# 2. INITIALIZE AGENTS
# =============================================

payment_agent = PaymentHistoryAgent()

validation_agent = DataValidationAgent()

decision_agent = DecisionAgent()

communication_agent = CommunicationAgent()

report_agent = ReportGenerationAgent()



def safe_log_agent(customer_id, agent_name, action, result):
    """Log execution without allowing a logging failure to stop the workflow."""
    try:
        log_agent_execution(customer_id, agent_name, action, result)
    except Exception as logging_error:
        print(f"[LOGGING ERROR] {agent_name}: {logging_error}")



def has_critical_upstream_failure(state: DebtManagementState) -> bool:
    """
    Return True when either upstream analysis agent failed.

    Validation is an independent safety check, but a successful validation
    should not silently override a failed customer/payment analysis stage.
    """
    critical_prefixes = ("Customer Analysis:", "Payment History:")
    errors = state.get("errors", []) or []

    return any(
        isinstance(error, str) and error.startswith(critical_prefixes)
        for error in errors
    )


# =============================================
# 3. CUSTOMER ANALYSIS NODE
# =============================================

def customer_analysis_node(state: DebtManagementState):

    print("\n[LANGGRAPH] Running Customer Analysis Agent...")

    try:

        customer_id = state["customer_id"]

        result = analyze_customer(customer_id)

        print("[LANGGRAPH] Customer Analysis completed.")
        safe_log_agent(customer_id, "Customer Analysis Agent",
                       "analyze_customer",
                       {"status": "SUCCESS", "output": result})
        return {
            "customer_analysis": result
        }

    except Exception as error:

        print("[ERROR] Customer Analysis:", error)
        safe_log_agent(state.get("customer_id"), "Customer Analysis Agent",
                       "analyze_customer",
                       {"status": "FAILED", "error": str(error)})
        return {
            "errors": [f"Customer Analysis: {str(error)}"]
        }


# =============================================
# 4. PAYMENT HISTORY NODE
# =============================================

def payment_history_node(state: DebtManagementState):

    print("\n[LANGGRAPH] Running Payment History Agent...")

    try:

        customer_id = state["customer_id"]

        result = payment_agent.generate_report(customer_id)

        if result is None:
            raise ValueError("Customer not found in payment records.")

        print("[LANGGRAPH] Payment History completed.")
        safe_log_agent(customer_id, "Payment History Agent",
                       "generate_report",
                       {"status": "SUCCESS", "output": result})
        return {
            "payment_analysis": result
        }

    except Exception as error:

        print("[ERROR] Payment History:", error)
        safe_log_agent(state.get("customer_id"), "Payment History Agent",
                       "generate_report",
                       {"status": "FAILED", "error": str(error)})
        return {
            "errors": [f"Payment History: {str(error)}"]
        }


# =============================================
# 5. DATA VALIDATION NODE
# =============================================

def data_validation_node(state: DebtManagementState):

    print("\n[LANGGRAPH] Running Data Validation Agent...")

    try:

        customer_id = state["customer_id"]

        result = validation_agent.validate_customer(customer_id)

        if not isinstance(result, dict):
            raise ValueError("Invalid data validation result.")

        print("[LANGGRAPH] Data Validation completed.")

        print(
            "Validation Status:",
            result.get("validation_status")
        )

        print(
            "Total Issues:",
            result.get("total_issues")
        )
        safe_log_agent(customer_id, "Data Validation Agent",
                       "validate_customer",
                       {"status": "SUCCESS", "output": result})
        return {
            "data_validation": result
        }

    except Exception as error:

        print("[ERROR] Data Validation:", error)
        safe_log_agent(state.get("customer_id"), "Data Validation Agent",
                       "validate_customer",
                       {"status": "FAILED", "error": str(error)})
        # Fail-safe:
        # If validation itself fails, block communication.

        failed_validation = {
            "customer_id": state["customer_id"],
            "validation_status": "FAILED",
            "total_issues": 1,
            "error_count": 1,
            "warning_count": 0,
            "issues": [
                {
                    "severity": "ERROR",
                    "code": "validation_agent_failure",
                    "message": (
                        "Data Validation Agent failed. "
                        "Manual review is required."
                    )
                }
            ]
        }

        return {
            "data_validation": failed_validation,
            "errors": [f"Data Validation: {str(error)}"]
        }


# =============================================
# 6. DECISION AGENT NODE
# =============================================

def decision_node(state: DebtManagementState):

    print("\n[LANGGRAPH] Running Decision Agent...")

    try:

        customer_id = state["customer_id"]

        validation = state.get("data_validation", {})

        validation_status = validation.get(
            "validation_status",
            "FAILED"
        )

        # SAFETY GATE:
        # Do not allow automated communication if
        # financial data has warnings or errors.

        upstream_failure = has_critical_upstream_failure(state)

        if validation_status != "PASSED" or upstream_failure:

            print(
                "[LANGGRAPH] Validation or an upstream analysis stage did not pass."
            )

            print(
                "[LANGGRAPH] Overriding decision to Manual Review."
            )

            issues = validation.get("issues", [])

            issue_messages = [
                issue.get("message", "Unspecified validation issue")
                for issue in issues
            ]

            fallback_reason = (
                "Data validation status is "
                f"{validation_status}. "
                "Financial records require human verification."
            )

            if upstream_failure:
                fallback_reason += (
                    " Customer Analysis or Payment History failed; "
                    "the workflow requires human review."
                )

            if issue_messages:
                fallback_reason += " Issues: " + " | ".join(
                    issue_messages
                )

            # Retrieve the recorded loan details so the manual-review
            # override does not discard useful context from the Decision Agent.
            customer_context = decision_agent.get_customer_data(customer_id) or {}

            manual_review_decision = {
                "customer_id": customer_id,
                "customer_name": customer_context.get("name"),
                "loan_id": customer_context.get("loan_id"),
                "loan_status": customer_context.get("status"),
                "outstanding_amount": customer_context.get("outstanding_amount"),
                "due_date": customer_context.get("due_date"),
                "action": "manual_review",
                "priority": "High",
                "reason": fallback_reason,
                "communication_required": False,
                "human_review_required": True,
                "validation_status": validation_status,
                "upstream_analysis_failure": upstream_failure
            }

            safe_log_agent(customer_id, "Decision Agent", "make_decision",
                           {"status": "COMPLETED_MANUAL_REVIEW",
                            "output": manual_review_decision})
            return {
                "decision": manual_review_decision
            }

        # Run normal decision logic only when
        # data validation has passed.

        result = decision_agent.make_decision(customer_id)

        if not isinstance(result, dict):
            raise ValueError("Invalid decision result.")

        result["validation_status"] = validation_status

        print("[LANGGRAPH] Decision Agent completed.")

        print("Recommended Action:", result.get("action"))

        print("Priority:", result.get("priority"))
        safe_log_agent(customer_id, "Decision Agent", "make_decision",
                       {"status": "SUCCESS", "output": result})
        return {
            "decision": result
        }

    except Exception as error:

        print("[ERROR] Decision Agent:", error)
        safe_log_agent(state.get("customer_id"), "Decision Agent",
                       "make_decision",
                       {"status": "FAILED", "error": str(error)})
        # If decision logic fails, require human review.

        fallback_decision = {

            "customer_id": state["customer_id"],

            "action": "manual_review",

            "priority": "High",

            "reason": "Decision Agent failed. Human review is required.",

            "communication_required": False,

            "human_review_required": True
        }

        return {
            "decision": fallback_decision,
            "errors": [f"Decision Agent: {str(error)}"]
        }


# =============================================
# 7. CONDITIONAL ROUTING
# =============================================

def route_after_decision(state: DebtManagementState):

    decision = state.get("decision", {})
    validation = state.get("data_validation", {})

    validation_status = validation.get(
        "validation_status",
        "FAILED"
    )

    communication_required = decision.get(
        "communication_required",
        False
    )

    customer_id = state.get("customer_id")

    upstream_failure = has_critical_upstream_failure(state)

    # Defense-in-depth: require passed validation, successful upstream
    # analysis, and explicit authorization from the Decision Agent.
    if (
        validation_status == "PASSED"
        and not upstream_failure
        and communication_required
    ):
        print("\n[LANGGRAPH] Routing to Communication Agent...")
        return "communication"

    # The conditional edge bypasses the Communication node entirely.
    # Record that bypass so the audit trail shows every workflow decision.
    if validation_status != "PASSED":
        skip_reason = (
            "Communication was skipped because data validation "
            f"status was '{validation_status}'. Human review is required."
        )
    elif upstream_failure:
        skip_reason = (
            "Communication was skipped because Customer Analysis or "
            "Payment History failed. Human review is required."
        )
    else:
        skip_reason = (
            "Communication was skipped because the Decision Agent "
            "did not authorize or require communication."
        )

    print("\n[LANGGRAPH] Communication not authorized or not required.")
    print("[LANGGRAPH] Skipping Communication Agent...")

    safe_log_agent(
        customer_id,
        "Communication Agent",
        "generate_message",
        {
            "status": "SKIPPED",
            "reason": skip_reason,
            "validation_status": validation_status,
            "upstream_analysis_failure": upstream_failure,
            "communication_required": communication_required
        }
    )

    return "report_generation"


# 8. COMMUNICATION NODE
# =============================================

def communication_node(state: DebtManagementState):

    print("\n[LANGGRAPH] Running Communication Agent...")

    try:

        customer_id = state["customer_id"]

        decision = state.get("decision", {})

        validation = state.get("data_validation", {})

        # Safety checks before generating a message.

        if validation.get("validation_status") != "PASSED":

            print(
                "[LANGGRAPH] Data validation has not passed."
            )

            safe_log_agent(customer_id, "Communication Agent",
                           "generate_message",
                           {"status": "SKIPPED",
                            "reason": "Data validation did not pass"})
            return {
                "communication_draft": None
            }

        if has_critical_upstream_failure(state):
            safe_log_agent(
                customer_id,
                "Communication Agent",
                "generate_message",
                {
                    "status": "SKIPPED",
                    "reason": (
                        "Customer Analysis or Payment History failed; "
                        "human review is required."
                    )
                }
            )
            return {"communication_draft": None}

        if not decision.get("communication_required", False):

            print(
                "[LANGGRAPH] Communication not authorized by decision."
            )

            safe_log_agent(customer_id, "Communication Agent",
                           "generate_message",
                           {"status": "SKIPPED",
                            "reason": "Decision did not authorize communication"})
            return {
                "communication_draft": None
            }

        result = communication_agent.generate_message(customer_id)

        if not isinstance(result, dict):
            raise ValueError(str(result))

        # Keep human approval mandatory.

        result["approval_status"] = "Pending Human Approval"

        print("[LANGGRAPH] Communication Agent completed.")
        safe_log_agent(customer_id, "Communication Agent",
                       "generate_message",
                       {"status": "SUCCESS",
                        "approval_status": result.get("approval_status")})
        return {
            "communication_draft": result
        }

    except Exception as error:

        print("[ERROR] Communication Agent:", error)
        safe_log_agent(state.get("customer_id"), "Communication Agent",
                       "generate_message",
                       {"status": "FAILED", "error": str(error)})
        return {
            "communication_draft": None,
            "errors": [f"Communication Agent: {str(error)}"]
        }


# =============================================
# 9. REPORT GENERATION NODE
# =============================================

def report_generation_node(state: DebtManagementState):

    print("\n[LANGGRAPH] Running Report Generation Agent...")

    try:

        customer_id = state["customer_id"]

        communication_draft = state.get("communication_draft")

        result = report_agent.generate_report(
            customer_id,
            communication_draft=communication_draft
        )

        if result is None:
            raise ValueError("Unable to generate customer report.")

        if not isinstance(result, dict):
            raise ValueError("Report Generation Agent returned an invalid result.")

        required_report_fields = {
            "customer_id",
            "customer_name",
            "financial_metrics",
            "analysis",
        }
        missing_fields = required_report_fields.difference(result.keys())

        if missing_fields:
            raise ValueError(
                "Generated report is missing required fields: "
                + ", ".join(sorted(missing_fields))
            )

        if not isinstance(result.get("financial_metrics"), dict):
            raise ValueError("Report financial_metrics must be a dictionary.")

        print("[LANGGRAPH] Report Generation completed.")
        safe_log_agent(customer_id, "Report Generation Agent",
                       "generate_report",
                       {"status": "SUCCESS",
                        "customer_id": result.get("customer_id")})
        return {
            "final_report": result
        }

    except Exception as error:

        print("[ERROR] Report Generation:", error)
        safe_log_agent(state.get("customer_id"), "Report Generation Agent",
                       "generate_report",
                       {"status": "FAILED", "error": str(error)})
        return {
            "errors": [f"Report Generation: {str(error)}"]
        }


# =============================================
# 10. BUILD LANGGRAPH WORKFLOW
# =============================================

def build_workflow():

    workflow = StateGraph(DebtManagementState)

    # Register nodes

    workflow.add_node(
        "customer_analysis",
        customer_analysis_node
    )

    workflow.add_node(
        "payment_history",
        payment_history_node
    )

    workflow.add_node(
        "data_validation",
        data_validation_node
    )

    workflow.add_node(
        "decision",
        decision_node
    )

    workflow.add_node(
        "communication",
        communication_node
    )

    workflow.add_node(
        "report_generation",
        report_generation_node
    )

    # Define execution order

    workflow.add_edge(
        START,
        "customer_analysis"
    )

    workflow.add_edge(
        "customer_analysis",
        "payment_history"
    )

    workflow.add_edge(
        "payment_history",
        "data_validation"
    )

    workflow.add_edge(
        "data_validation",
        "decision"
    )

    # Conditional routing based on validation and decision.

    workflow.add_conditional_edges(
        "decision",
        route_after_decision,
        {
            "communication": "communication",
            "report_generation": "report_generation"
        }
    )

    workflow.add_edge(
        "communication",
        "report_generation"
    )

    workflow.add_edge(
        "report_generation",
        END
    )

    return workflow.compile()


# =============================================
# 11. EXECUTE WORKFLOW
# =============================================

def run_debt_management(customer_id):

    app = build_workflow()

    initial_state = {

        "customer_id": customer_id,

        "errors": []

    }

    print("\n==============================================")

    print("       AI DEBT MANAGEMENT WORKFLOW")

    print("==============================================")

    print("\nStarting LangGraph execution...")

    result = app.invoke(initial_state)

    print("\n==============================================")

    print("          WORKFLOW EXECUTION SUMMARY")

    print("==============================================")

    # Build an accurate execution summary from the final workflow state.
    # A validation WARNING is not an agent failure: it is a completed
    # validation that correctly triggers manual review.
    errors = result.get("errors", []) or []

    def has_error(agent_label):
        return any(
            str(error).lower().startswith(agent_label.lower() + ":")
            for error in errors
        )

    execution_statuses = []

    stage_definitions = [
        ("Customer Analysis Agent", "customer_analysis", "Customer Analysis"),
        ("Payment History Agent", "payment_analysis", "Payment History"),
        ("Data Validation Agent", "data_validation", "Data Validation"),
        ("Decision Agent", "decision", "Decision Agent"),
    ]

    for agent_name, state_key, error_label in stage_definitions:
        if has_error(error_label):
            status = "FAILED"
        elif result.get(state_key) is not None:
            status = "COMPLETED"
        else:
            status = "NOT_COMPLETED"
        execution_statuses.append((agent_name, status))

    communication = result.get("communication_draft")
    if has_error("Communication Agent"):
        communication_status = "FAILED"
    elif isinstance(communication, dict):
        communication_status = "COMPLETED"
    else:
        # Conditional routing bypassed the Communication Agent.
        communication_status = "SKIPPED"
    execution_statuses.append(("Communication Agent", communication_status))

    if has_error("Report Generation"):
        report_status = "FAILED"
    elif result.get("final_report") is not None:
        report_status = "COMPLETED"
    else:
        report_status = "NOT_COMPLETED"
    execution_statuses.append(("Report Generation Agent", report_status))

    completed_count = sum(
        status == "COMPLETED" for _, status in execution_statuses
    )
    skipped_count = sum(
        status == "SKIPPED" for _, status in execution_statuses
    )
    failed_count = sum(
        status == "FAILED" for _, status in execution_statuses
    )
    not_completed_count = sum(
        status == "NOT_COMPLETED" for _, status in execution_statuses
    )

    print("\nAGENT EXECUTION STATUS")
    print("----------------------------------------------")
    for agent_name, status in execution_statuses:
        print(f"{agent_name}: {status}")

    print("\nEXECUTION COUNTS")
    print("----------------------------------------------")
    print(f"Completed: {completed_count}")
    print(f"Skipped: {skipped_count}")
    print(f"Failed: {failed_count}")
    print(f"Not completed: {not_completed_count}")

    if errors:
        print("\nErrors encountered:")
        for error in errors:
            print("-", error)
    elif skipped_count:
        print("\nWorkflow completed with intentional agent skips.")
    else:
        print("\nAll workflow agents completed successfully.")

    # Display Data Validation result

    validation = result.get("data_validation")

    if validation:

        print("\nDATA VALIDATION RESULT")

        print("----------------------------------------------")

        print(
            "Validation Status:",
            validation.get("validation_status")
        )

        print(
            "Total Issues:",
            validation.get("total_issues")
        )

        for issue in validation.get("issues", []):

            print(
                issue.get("severity"),
                "-",
                issue.get("message")
            )

    # Display Decision Agent result

    decision = result.get("decision")

    if decision:

        print("\nDECISION AGENT RESULT")

        print("----------------------------------------------")

        for key, value in decision.items():
            print(f"{key}: {value}")

    # Display final report

    final_report = result.get("final_report")

    if final_report:

        print("\nCUSTOMER:", final_report["customer_name"])

        print("CUSTOMER ID:", final_report["customer_id"])

        print("\nFINANCIAL METRICS")

        print("----------------------------------------------")

        metrics = final_report["financial_metrics"]

        for key, value in metrics.items():
            print(f"{key}: {value}")

        print("\nAI FINANCIAL ANALYSIS")

        print("----------------------------------------------")

        print(final_report["analysis"])

        print("\nCOMMUNICATION DRAFT")

        print("----------------------------------------------")

        communication = final_report.get("communication_draft")

        if isinstance(communication, dict):

            print(communication["message_draft"])

            print(
                "\nApproval Status:",
                communication.get("approval_status")
            )

        elif communication is None:

            print("No communication draft generated.")

        else:

            print(communication)

    else:

        print("\nFinal report could not be generated.")

    print("\n==============================================")

    print("          WORKFLOW COMPLETED")

    print("==============================================")

    # Return the final LangGraph state so callers can inspect results
    # without parsing console output or invoking the graph a second time.
    return result


# =============================================
# 12. MAIN PROGRAM
# =============================================

if __name__ == "__main__":

    try:

        customer_id = int(
            input("\nEnter Customer ID (1-4): ")
        )

        run_debt_management(customer_id)

    except ValueError:

        print("\nPlease enter a valid numeric Customer ID.")

    except Exception as error:

        print("\nWorkflow execution failed:", error)