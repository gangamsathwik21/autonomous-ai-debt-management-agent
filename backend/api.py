"""FastAPI interface for the Autonomous AI Debt Management Agent.

Security notes:
- Protected endpoints require the X-API-Key header.
- The key is read from DEBT_API_KEY on each request so it can be rotated
  without changing source code (restart the server after rotation).
- Customer records are synthetic demo data in the current MVP.
- Communication approval records a human decision only; it never sends a
  message to a customer.
"""

from contextlib import asynccontextmanager
import logging
import os
import secrets
from typing import Literal, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Path, Query
from pydantic import BaseModel, Field, field_validator

from backend.database import get_agent_logs, get_connection
from workflows.debt_workflow import build_workflow


logger = logging.getLogger(__name__)


# Compile the LangGraph workflow once per API process.
workflow_app = build_workflow()


# ---------------------------------------------------------------------------
# Database helpers and application lifecycle
# ---------------------------------------------------------------------------

def get_api_db_connection():
    """Return a database connection with SQLite foreign-key checks enabled."""
    connection = get_connection()
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        return connection
    except Exception:
        connection.close()
        raise


def _is_positive_integer(value) -> bool:
    """Return True for positive integers, excluding bool values."""
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _get_persistable_communication_draft(result: dict, customer_id: int):
    """Validate workflow output before allowing a draft into the review queue.

    The API independently enforces the workflow's safety conditions. It does
    not trust the presence of a draft alone as authorization to persist it.
    """
    validation = result.get("data_validation")
    decision = result.get("decision")
    draft = result.get("communication_draft")

    if not isinstance(validation, dict) or validation.get("validation_status") != "PASSED":
        return None

    if not isinstance(decision, dict):
        return None

    if decision.get("communication_required") is not True:
        return None

    if decision.get("human_review_required") is not True:
        return None

    loan_id = decision.get("loan_id")
    if not _is_positive_integer(loan_id):
        return None

    if not isinstance(draft, dict):
        return None

    message_text = draft.get("message_draft")
    if not isinstance(message_text, str) or not message_text.strip():
        return None

    if draft.get("approval_status") != "Pending Human Approval":
        return None

    return {"loan_id": loan_id, "message_text": message_text.strip()}


def initialize_approval_table():
    """Create the communication approval table and its lookup index."""
    connection = get_api_db_connection()
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS communication_approvals (
                approval_id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                loan_id INTEGER,
                message_draft TEXT NOT NULL CHECK (length(trim(message_draft)) > 0),
                approval_status TEXT NOT NULL DEFAULT 'Pending Human Approval'
                    CHECK (approval_status IN (
                        'Pending Human Approval', 'Approved', 'Rejected'
                    )),
                reviewer_name TEXT,
                review_notes TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                reviewed_at TEXT,
                FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_communication_approvals_status_created
            ON communication_approvals (approval_status, created_at DESC)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_communication_approvals_customer_created
            ON communication_approvals (customer_id, created_at DESC)
            """
        )
        connection.commit()
    except Exception:
        connection.rollback()
        logger.exception("Could not initialize communication approval storage")
        raise
    finally:
        connection.close()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Initialize API-owned database objects during application startup."""
    initialize_approval_table()
    yield


app = FastAPI(
    title="Autonomous AI Debt Management Agent",
    description="AI-powered debt management system using LangGraph and Ollama",
    version="2.1.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

def verify_api_key(x_api_key: Optional[str] = Header(default=None)):
    """Validate the X-API-Key header against the configured environment key."""
    expected_key = os.getenv("DEBT_API_KEY")

    if not expected_key:
        logger.error("DEBT_API_KEY is not configured")
        raise HTTPException(
            status_code=500,
            detail="API authentication is not configured.",
        )

    if not x_api_key or not secrets.compare_digest(x_api_key, expected_key):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    return True


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class CommunicationReviewRequest(BaseModel):
    decision: Literal["approve", "reject"]
    reviewer_name: str = Field(min_length=2, max_length=100)
    review_notes: Optional[str] = Field(default=None, max_length=1000)

    @field_validator("reviewer_name")
    @classmethod
    def validate_reviewer_name(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError(
                "Reviewer name must contain at least 2 non-space characters."
            )
        return cleaned

    @field_validator("review_notes")
    @classmethod
    def clean_review_notes(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


# ---------------------------------------------------------------------------
# Public operational endpoints
# ---------------------------------------------------------------------------

@app.get("/")
def home():
    return {
        "message": "Autonomous AI Debt Management API is running",
        "status": "online",
        "version": "2.1.0",
    }


@app.get("/health")
def health_check():
    connection = None
    try:
        connection = get_api_db_connection()
        connection.execute("SELECT 1")
        return {"status": "healthy", "database": "connected"}
    except Exception:
        logger.exception("Database health check failed")
        raise HTTPException(
            status_code=500,
            detail="Database health check failed.",
        )
    finally:
        if connection is not None:
            connection.close()


# ---------------------------------------------------------------------------
# Customer endpoints (authenticated)
# ---------------------------------------------------------------------------

@app.get("/customers", dependencies=[Depends(verify_api_key)])
def get_customers():
    connection = get_api_db_connection()
    try:
        rows = connection.execute(
            """
            SELECT
                c.customer_id,
                c.name,
                c.email,
                c.phone,
                c.monthly_income,
                c.employment_status,
                l.loan_id,
                l.loan_amount,
                l.outstanding_amount,
                l.due_date,
                l.status AS loan_status
            FROM customers AS c
            LEFT JOIN loans AS l ON c.customer_id = l.customer_id
            ORDER BY c.customer_id, l.loan_id
            """
        ).fetchall()
        return [dict(row) for row in rows]
    except Exception:
        logger.exception("Could not retrieve customer list")
        raise HTTPException(
            status_code=500,
            detail="Could not retrieve customers.",
        )
    finally:
        connection.close()


@app.get("/customers/{customer_id}", dependencies=[Depends(verify_api_key)])
def get_customer(customer_id: int = Path(..., ge=1)):
    connection = get_api_db_connection()
    try:
        customer = connection.execute(
            """
            SELECT customer_id, name, email, phone, monthly_income, employment_status
            FROM customers
            WHERE customer_id = ?
            """,
            (customer_id,),
        ).fetchone()

        if customer is None:
            raise HTTPException(status_code=404, detail="Customer not found")

        loans = connection.execute(
            """
            SELECT loan_id, customer_id, loan_amount, outstanding_amount,
                   due_date, interest_rate, status
            FROM loans
            WHERE customer_id = ?
            ORDER BY loan_id
            """,
            (customer_id,),
        ).fetchall()

        loan_details = []
        for loan in loans:
            loan_data = dict(loan)
            payments = connection.execute(
                """
                SELECT payment_id, loan_id, amount, payment_date, status
                FROM payments
                WHERE loan_id = ?
                ORDER BY payment_date, payment_id
                """,
                (loan["loan_id"],),
            ).fetchall()
            loan_data["payments"] = [dict(payment) for payment in payments]
            loan_details.append(loan_data)

        return {"customer": dict(customer), "loans": loan_details}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Could not retrieve customer details for customer_id=%s", customer_id)
        raise HTTPException(
            status_code=500,
            detail="Could not retrieve customer details.",
        )
    finally:
        connection.close()


# ---------------------------------------------------------------------------
# Agent execution logs
# ---------------------------------------------------------------------------

@app.get("/agent-logs", dependencies=[Depends(verify_api_key)])
def get_execution_logs(
    customer_id: Optional[int] = Query(default=None, ge=1),
    limit: int = Query(default=100, ge=1, le=500),
):
    try:
        logs = get_agent_logs(customer_id=customer_id, limit=limit)
        return {
            "total_logs": len(logs),
            "customer_id": customer_id,
            "logs": [dict(log) for log in logs],
        }
    except Exception:
        logger.exception("Could not retrieve agent execution logs")
        raise HTTPException(
            status_code=500,
            detail="Could not retrieve agent logs.",
        )


# ---------------------------------------------------------------------------
# Run the LangGraph debt-management workflow
# ---------------------------------------------------------------------------

@app.post("/analyze/{customer_id}", dependencies=[Depends(verify_api_key)])
def analyze_customer(customer_id: int = Path(..., ge=1)):
    # Check that the customer exists before running the comparatively expensive workflow.
    connection = get_api_db_connection()
    try:
        customer = connection.execute(
            "SELECT customer_id FROM customers WHERE customer_id = ?",
            (customer_id,),
        ).fetchone()
        if customer is None:
            raise HTTPException(status_code=404, detail="Customer not found")
    except HTTPException:
        raise
    except Exception:
        logger.exception("Could not verify customer_id=%s before analysis", customer_id)
        raise HTTPException(
            status_code=500,
            detail="Could not verify customer before analysis.",
        )
    finally:
        connection.close()

    try:
        result = workflow_app.invoke({"customer_id": customer_id, "errors": []})
        if not isinstance(result, dict):
            raise ValueError("Workflow returned an invalid result")

        persistable_draft = _get_persistable_communication_draft(result, customer_id)
        if persistable_draft is not None:
            loan_id = persistable_draft["loan_id"]
            message_text = persistable_draft["message_text"]
            approval_connection = get_api_db_connection()
            try:
                # Verify ownership inside the same write transaction as the
                # duplicate check and insert. BEGIN IMMEDIATE serializes writers.
                approval_connection.execute("BEGIN IMMEDIATE")
                owned_loan = approval_connection.execute(
                    "SELECT loan_id FROM loans WHERE loan_id = ? AND customer_id = ?",
                    (loan_id, customer_id),
                ).fetchone()

                if owned_loan is None:
                    logger.warning(
                        "Blocked communication draft with loan/customer mismatch: "
                        "customer_id=%s loan_id=%s",
                        customer_id,
                        loan_id,
                    )
                else:
                    existing_pending = approval_connection.execute(
                        """
                        SELECT approval_id
                        FROM communication_approvals
                        WHERE customer_id = ?
                          AND loan_id = ?
                          AND approval_status = 'Pending Human Approval'
                        LIMIT 1
                        """,
                        (customer_id, loan_id),
                    ).fetchone()

                    if existing_pending is None:
                        approval_connection.execute(
                            """
                            INSERT INTO communication_approvals (
                                customer_id, loan_id, message_draft, approval_status
                            ) VALUES (?, ?, ?, 'Pending Human Approval')
                            """,
                            (customer_id, loan_id, message_text),
                        )
                approval_connection.commit()
            except Exception:
                approval_connection.rollback()
                raise
            finally:
                approval_connection.close()

        workflow_errors = result.get("errors", [])
        if not isinstance(workflow_errors, list):
            workflow_errors = ["Workflow reported an unexpected error format."]

        # Preserve the workflow's structured error messages for the dashboard.
        # Detailed stack traces are logged server-side and never returned here.
        safe_errors = [
            str(error)[:500]
            for error in workflow_errors
            if isinstance(error, (str, int, float))
        ]

        return {
            "status": "completed" if result.get("final_report") else "completed_with_errors",
            "customer_id": customer_id,
            "customer_analysis": result.get("customer_analysis"),
            "payment_analysis": result.get("payment_analysis"),
            "data_validation": result.get("data_validation"),
            "decision": result.get("decision"),
            "communication_draft": result.get("communication_draft"),
            "final_report": result.get("final_report"),
            "errors": safe_errors,
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Workflow execution failed for customer_id=%s", customer_id)
        raise HTTPException(
            status_code=500,
            detail="Workflow execution failed. Check the backend terminal logs.",
        )


# ---------------------------------------------------------------------------
# Communication approval queue
# ---------------------------------------------------------------------------

@app.get("/communications/pending", dependencies=[Depends(verify_api_key)])
def get_pending_communications():
    connection = get_api_db_connection()
    try:
        rows = connection.execute(
            """
            SELECT
                a.approval_id,
                a.customer_id,
                c.name AS customer_name,
                c.email AS customer_email,
                a.loan_id,
                a.message_draft,
                a.approval_status,
                a.created_at
            FROM communication_approvals AS a
            JOIN customers AS c ON c.customer_id = a.customer_id
            WHERE a.approval_status = 'Pending Human Approval'
            ORDER BY a.created_at DESC, a.approval_id DESC
            LIMIT 500
            """
        ).fetchall()
        return {
            "total_pending": len(rows),
            "communications": [dict(row) for row in rows],
        }
    except Exception:
        logger.exception("Could not retrieve pending communications")
        raise HTTPException(
            status_code=500,
            detail="Could not retrieve pending communications.",
        )
    finally:
        connection.close()


# ---------------------------------------------------------------------------
# Approve or reject a communication draft
# ---------------------------------------------------------------------------

@app.post(
    "/communications/{approval_id}/review",
    dependencies=[Depends(verify_api_key)],
)
def review_communication(
    review: CommunicationReviewRequest,
    approval_id: int = Path(..., ge=1),
):
    connection = get_api_db_connection()
    try:
        # Acquire the SQLite write lock before reading status. This ensures
        # concurrent reviewers cannot both act on the same pending record.
        connection.execute("BEGIN IMMEDIATE")
        existing = connection.execute(
            """
            SELECT approval_id, customer_id, approval_status
            FROM communication_approvals
            WHERE approval_id = ?
            """,
            (approval_id,),
        ).fetchone()

        if existing is None:
            connection.rollback()
            raise HTTPException(
                status_code=404,
                detail="Communication approval record not found.",
            )

        if existing["approval_status"] != "Pending Human Approval":
            connection.rollback()
            raise HTTPException(
                status_code=409,
                detail="This communication has already been reviewed.",
            )

        new_status = "Approved" if review.decision == "approve" else "Rejected"

        cursor = connection.execute(
            """
            UPDATE communication_approvals
            SET approval_status = ?,
                reviewer_name = ?,
                review_notes = ?,
                reviewed_at = CURRENT_TIMESTAMP
            WHERE approval_id = ?
              AND approval_status = 'Pending Human Approval'
            """,
            (new_status, review.reviewer_name, review.review_notes, approval_id),
        )

        if cursor.rowcount != 1:
            connection.rollback()
            raise HTTPException(
                status_code=409,
                detail="This communication has already been reviewed.",
            )

        connection.commit()
        updated = connection.execute(
            """
            SELECT approval_id, customer_id, loan_id, approval_status,
                   reviewer_name, review_notes, created_at, reviewed_at
            FROM communication_approvals
            WHERE approval_id = ?
            """,
            (approval_id,),
        ).fetchone()

        return {
            "message": f"Communication draft {new_status.lower()} successfully.",
            "review": dict(updated),
            "communication_sent": False,
        }
    except HTTPException:
        raise
    except Exception:
        connection.rollback()
        logger.exception("Could not review communication approval_id=%s", approval_id)
        raise HTTPException(
            status_code=500,
            detail="Could not review communication.",
        )
    finally:
        connection.close()


# ---------------------------------------------------------------------------
# Communication review history
# ---------------------------------------------------------------------------

@app.get("/communications/history", dependencies=[Depends(verify_api_key)])
def get_communication_history(
    customer_id: Optional[int] = Query(default=None, ge=1),
    limit: int = Query(default=100, ge=1, le=500),
):
    connection = get_api_db_connection()
    try:
        base_query = """
            SELECT approval_id, customer_id, loan_id, message_draft,
                   approval_status, reviewer_name, review_notes,
                   created_at, reviewed_at
            FROM communication_approvals
        """
        if customer_id is not None:
            rows = connection.execute(
                base_query
                + " WHERE customer_id = ? ORDER BY created_at DESC, approval_id DESC LIMIT ?",
                (customer_id, limit),
            ).fetchall()
        else:
            rows = connection.execute(
                base_query + " ORDER BY created_at DESC, approval_id DESC LIMIT ?",
                (limit,),
            ).fetchall()

        return {
            "total_records": len(rows),
            "customer_id": customer_id,
            "history": [dict(row) for row in rows],
        }
    except Exception:
        logger.exception("Could not retrieve communication review history")
        raise HTTPException(
            status_code=500,
            detail="Could not retrieve communication history.",
        )
    finally:
        connection.close()
