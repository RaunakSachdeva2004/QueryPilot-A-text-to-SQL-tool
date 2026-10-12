# Architectural Decisions Log

## Phase 1: Foundation
- **Built**: Project setup (`pyproject.toml`, `uv.lock`), config (`pydantic-settings`), security policy, structured logging (`structlog`), Postgres 16 docker-compose, SQLAlchemy 2.x models, initial Alembic migration with dual DB roles, deterministic seed script, and read-only verification suite.
- **Key Choices**: Separated owner role (`querypilot`) from read-only role (`querypilot_ro`) at Postgres DDL level; granted column-level SELECT on `customers` excluding PII `email`; enforced `default_transaction_read_only=on`, `statement_timeout=5000ms`, `timezone=UTC` on `querypilot_ro`; denied metadata tables (`query_runs`, `alembic_version`, checkpoints).
- **Tested Versions**: `fastapi==0.143.0`, `sqlglot==26.33.0`, `sqlalchemy==2.1.4`, `psycopg==3.3.6`, `alembic==1.20.0`, `langgraph==0.6.11`, `langgraph-checkpoint-postgres==2.0.25`, `pydantic==2.14.1`, `structlog==24.4.0`.
- **Known Limitations**: Seed uses static cost prices; historical price fluctuations not modeled; cross-session query history not supported in v1.
