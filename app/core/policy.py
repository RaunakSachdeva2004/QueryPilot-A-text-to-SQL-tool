"""
SQL security policy: allowlists, blocklists, and business rules.

This module is the single source of truth for what the SQL validator permits.
It does NOT perform validation itself — sql_validator.py reads these constants.
"""

from __future__ import annotations

# ────────────────────────────────────────────────────────────
# Table allowlist  (schema-qualified → set of allowed columns)
# ────────────────────────────────────────────────────────────

ALLOWED_TABLES: dict[str, set[str]] = {
    "customers": {"id", "name", "created_at", "city"},
    # NOTE: customers.email is deliberately excluded (PII)
    "products": {"id", "name", "category", "cost_price"},
    "orders": {"id", "customer_id", "order_date", "status", "total_amount"},
    "order_items": {"id", "order_id", "product_id", "quantity", "unit_price"},
}

# Flat set of allowed table names (for quick lookup)
ALLOWED_TABLE_NAMES: set[str] = set(ALLOWED_TABLES.keys())

# Every allowed column across all tables (for unqualified column checks)
ALL_ALLOWED_COLUMNS: set[str] = set()
for _cols in ALLOWED_TABLES.values():
    ALL_ALLOWED_COLUMNS |= _cols

# ────────────────────────────────────────────────────────────
# Restricted / PII columns  (table.column format)
# ────────────────────────────────────────────────────────────

RESTRICTED_COLUMNS: set[str] = {"customers.email"}

# ────────────────────────────────────────────────────────────
# Forbidden schemas
# ────────────────────────────────────────────────────────────

FORBIDDEN_SCHEMAS: set[str] = {
    "pg_catalog",
    "information_schema",
    "pg_toast",
    "pg_temp",
}

# ────────────────────────────────────────────────────────────
# Forbidden functions
# ────────────────────────────────────────────────────────────

FORBIDDEN_FUNCTIONS: set[str] = {
    # System / sleep
    "pg_sleep",
    "pg_sleep_for",
    "pg_sleep_until",
    "set_config",
    "current_setting",
    # Remote access
    "dblink",
    "dblink_exec",
    "dblink_connect",
    # Large object
    "lo_import",
    "lo_export",
    "lo_unlink",
    "lo_create",
    # Advisory locks
    "pg_advisory_lock",
    "pg_advisory_unlock",
    "pg_try_advisory_lock",
    # Copy
    "pg_read_file",
    "pg_read_binary_file",
    "pg_write_file",
    "pg_ls_dir",
    # Generic pg_* prefix catch (checked separately with startswith)
}

# Functions that start with these prefixes are forbidden
FORBIDDEN_FUNCTION_PREFIXES: tuple[str, ...] = ("pg_", "lo_")

# ────────────────────────────────────────────────────────────
# Forbidden statement types (anything that is not SELECT)
# ────────────────────────────────────────────────────────────

FORBIDDEN_STATEMENT_TYPES: set[str] = {
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "CREATE",
    "TRUNCATE",
    "GRANT",
    "REVOKE",
    "COPY",
    "CALL",
    "EXECUTE",
    "EXPLAIN",
    "VACUUM",
    "COMMENT",
    "SET",
    "MERGE",
}

# ────────────────────────────────────────────────────────────
# Internal/system tables the read-only role must NOT access
# ────────────────────────────────────────────────────────────

SYSTEM_TABLES: set[str] = {
    "query_runs",
    "alembic_version",
    # LangGraph checkpoint tables (created by AsyncPostgresSaver.setup())
    "checkpoints",
    "checkpoint_blobs",
    "checkpoint_writes",
    "checkpoint_migrations",
}

# ────────────────────────────────────────────────────────────
# Business rules
# ────────────────────────────────────────────────────────────

# Only orders with these statuses count towards revenue / profit / units sold
VALID_ORDER_STATUSES: set[str] = {"completed", "shipped"}

# All possible order statuses (for seed data)
ALL_ORDER_STATUSES: list[str] = ["pending", "completed", "shipped", "cancelled", "refunded"]

# ────────────────────────────────────────────────────────────
# Validation issue codes and retryability
# ────────────────────────────────────────────────────────────

# Validation-level issues that MAY be retried (the LLM can fix them)
RETRYABLE_VALIDATION_ISSUES: set[str] = {
    "parse_error",
    "unknown_table",
    "unknown_column",
    "star_not_allowed",
    "missing_limit",       # validator can add it, but if somehow produced
}

# Validation-level issues that must NEVER be retried (policy violations)
NON_RETRYABLE_VALIDATION_ISSUES: set[str] = {
    "multiple_statements",
    "non_select_statement",
    "restricted_column",
    "forbidden_schema",
    "forbidden_function",
    "write_in_cte",
    "table_function",
    "forbidden_table",
}

# PostgreSQL SQLSTATE codes that a corrected query could fix
RETRYABLE_SQLSTATES: set[str] = {
    "42601",  # syntax_error
    "42703",  # undefined_column
    "42P01",  # undefined_table
    "42883",  # undefined_function
    "42804",  # datatype_mismatch
    "42P08",  # ambiguous_parameter
    "42702",  # ambiguous_column
    "22P02",  # invalid_text_representation
    "22007",  # invalid_datetime_format
    "22003",  # numeric_value_out_of_range
}

# SQLSTATE codes that must NEVER be retried
NON_RETRYABLE_SQLSTATES: set[str] = {
    "57014",  # query_canceled (timeout)
    "25006",  # read_only_sql_transaction
    "42501",  # insufficient_privilege
    "42000",  # syntax_error_or_access_rule_violation (generic)
    "08006",  # connection_failure
}
