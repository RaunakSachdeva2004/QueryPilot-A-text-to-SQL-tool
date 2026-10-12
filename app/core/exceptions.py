"""
Application exception hierarchy.

All exceptions inherit from QueryPilotError so callers can catch broadly.
Each exception carries structured fields useful for logging and API responses.
"""

from __future__ import annotations


class QueryPilotError(Exception):
    """Base exception for all QueryPilot errors."""

    def __init__(self, message: str, *, detail: str | None = None) -> None:
        super().__init__(message)
        self.detail = detail


# ── SQL Validation ──────────────────────────────────────────


class SQLValidationError(QueryPilotError):
    """Raised when generated SQL fails structural/policy validation."""

    def __init__(
        self,
        message: str,
        *,
        issue_code: str,
        retryable: bool,
        detail: str | None = None,
    ) -> None:
        super().__init__(message, detail=detail)
        self.issue_code = issue_code
        self.retryable = retryable


class SQLPolicyViolation(SQLValidationError):
    """Non-retryable security policy violation (DML, restricted column, etc.)."""

    def __init__(self, message: str, *, issue_code: str, detail: str | None = None) -> None:
        super().__init__(message, issue_code=issue_code, retryable=False, detail=detail)


# ── SQL Execution ───────────────────────────────────────────


class SQLExecutionError(QueryPilotError):
    """Raised when SQL execution fails at the database level."""

    def __init__(
        self,
        message: str,
        *,
        sqlstate: str | None = None,
        retryable: bool,
        detail: str | None = None,
    ) -> None:
        super().__init__(message, detail=detail)
        self.sqlstate = sqlstate
        self.retryable = retryable


class SQLTimeoutError(SQLExecutionError):
    """Query exceeded the configured statement_timeout. Never retried."""

    def __init__(self, message: str = "Query timed out", *, detail: str | None = None) -> None:
        super().__init__(message, sqlstate="57014", retryable=False, detail=detail)


# ── Clarification / Workflow ────────────────────────────────


class ClarificationRequired(QueryPilotError):
    """The user's question needs clarification before SQL generation."""

    def __init__(
        self,
        message: str,
        *,
        question: str,
        options: list[str] | None = None,
        field: str | None = None,
    ) -> None:
        super().__init__(message)
        self.question = question
        self.options = options or []
        self.field = field


class MaxRetriesExhausted(QueryPilotError):
    """All correction attempts failed."""

    def __init__(self, message: str = "Max SQL retries exhausted") -> None:
        super().__init__(message)


class MaxClarificationRoundsExhausted(QueryPilotError):
    """Clarification round limit reached without resolution."""

    def __init__(self, message: str = "Max clarification rounds exhausted") -> None:
        super().__init__(message)


# ── LLM / Provider ─────────────────────────────────────────


class LLMProviderError(QueryPilotError):
    """Raised when the LLM provider call fails."""

    pass


# ── Query not found ─────────────────────────────────────────


class QueryNotFoundError(QueryPilotError):
    """Unknown query_id."""

    def __init__(self, query_id: str) -> None:
        super().__init__(f"Query not found: {query_id}")
        self.query_id = query_id
