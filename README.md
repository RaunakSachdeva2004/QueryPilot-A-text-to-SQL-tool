# QueryPilot: Production-Oriented Text-to-SQL and Clarification Engine

QueryPilot is an enterprise-grade natural-language-to-SQL system designed for querying relational business data in PostgreSQL. Unlike naive text-to-SQL prototypes that execute raw model outputs with elevated database privileges, QueryPilot is engineered around determinism, structural SQL validation, multi-layer security enforcement, human-in-the-loop clarification, and bounded error recovery.

---

## Table of Contents

- [Overview](#overview)
- [System Architecture](#system-architecture)
- [Core Engineering Tenets](#core-engineering-tenets)
- [Multi-Tier Security Architecture](#multi-tier-security-architecture)
  - [AST Parsing and Policy Validation](#ast-parsing-and-policy-validation)
  - [Dual Database Role Architecture](#dual-database-role-architecture)
  - [PII Protection and Schema Isolation](#pii-protection-and-schema-isolation)
- [Clarification and Ambiguity Engine](#clarification-and-ambiguity-engine)
- [Database Domain and Business Semantics](#database-domain-and-business-semantics)
- [Project Directory Layout](#project-directory-layout)
- [Environment Configuration](#environment-configuration)
- [Local Setup and Installation](#local-setup-and-installation)
- [Verification and Testing](#verification-and-testing)
- [Implementation Roadmap](#implementation-roadmap)
- [Platform and Compatibility Notes](#platform-and-compatibility-notes)

---

## Overview

Natural language database interfaces often fail in real-world scenarios due to three critical flaws:
1. **Semantic Ambiguity**: User requests such as "Which products performed best?" lack unambiguous definitions of performance (revenue vs. units sold vs. net profit) and time scope.
2. **Security Vulnerabilities**: Direct execution of unvalidated LLM output risks SQL injection, data leakage, unauthorized write operations, or denial-of-service via expensive queries.
3. **Fragile Execution**: Syntax mistakes or minor schema mismatches lead to abrupt query termination rather than controlled, bounded recovery.

QueryPilot eliminates these failure modes by combining:
- **Deterministic Ambiguity Detection and Clarification**: Intercepts under-specified questions before generation, requesting targeted human input via persistent LangGraph workflows.
- **Defense-in-Depth SQL Safety**: Enforces an AST validation pass with SQLGlot, strict table and column allowlists, function blocklists, and mandatory row limits.
- **Least-Privilege PostgreSQL Role Separation**: Validated queries execute strictly through a read-only role with column-level restrictions, forced UTC timezone, and statement execution timeouts.
- **Bounded Error Correction**: SQLSTATE-aware retry logic enables self-correction for recoverable syntax or schema mismatches without risking infinite loops or retrying policy violations.

---

## System Architecture

The following diagram illustrates the lifecycle of a query from user submission through ambiguity resolution, validation, execution, and factual response synthesis:

```mermaid
flowchart TD
    User([User Question]) --> API[FastAPI Layer: /api/v1/query]
    API --> Intent[Classify Intent & Detect Ambiguity]
    
    Intent -->|Ambiguity Detected| Interrupt[Interrupt Workflow: Emit Clarification]
    Interrupt --> UserClarify([User Selects Metric / Range])
    UserClarify --> Resume[FastAPI Layer: /clarify] --> ApplyClarify[Apply Clarification & Resolve Intent]
    
    Intent -->|Unambiguous| SchemaRet[Retrieve Schema & Glossary]
    ApplyClarify --> SchemaRet
    
    SchemaRet --> GenSQL[Generate SQL: LLM or Mock Provider]
    GenSQL --> ValSQL[SQLGlot AST Validation & Policy Check]
    
    ValSQL -->|Policy Violation| Reject([Reject Query: Non-Retryable Error])
    ValSQL -->|Retryable AST Error & Retries Remaining| CorrectSQL[Correct SQL Node]
    CorrectSQL --> ValSQL
    
    ValSQL -->|Valid AST| ExecSQL[Execute via Read-Only DB Role: querypilot_ro]
    
    ExecSQL -->|SQLSTATE Recoverable & Retries Remaining| CorrectSQL
    ExecSQL -->|Fatal SQLSTATE / Timeout / Max Retries| Fail([Fail Safely: Log Metadata])
    ExecSQL -->|Execution Success| Format[Synthesize Result & Factual Explanation]
    
    Format --> Persist[Persist Run Metadata to query_runs]
    Persist --> Response([Return Response Payload])
```

---

## Core Engineering Tenets

- **No Unchecked Model Outputs**: All SQL passed to the database must be parsed into an Abstract Syntax Tree (AST), checked against white-lists, and reconstructed by SQLGlot. Raw model strings are never executed directly.
- **No Superuser Query Execution**: Database migrations and application bookkeeping run under an administrative owner role, while generated queries run under a dedicated, unprivileged read-only role.
- **Deterministic Offline Mode**: Full workflow validation can be performed without external LLM API keys via an integrated mock provider.
- **Durable Workflow State**: Clarification cycles use LangGraph with PostgreSQL checkpointing, ensuring conversational state persists across service restarts.
- **Factual Result Reporting**: Explanations are strictly grounded in executed query tabular data. Speculative commentary or hallucinated records are prohibited.

---

## Multi-Tier Security Architecture

### AST Parsing and Policy Validation

QueryPilot implements structural SQL validation using SQLGlot configured for the PostgreSQL dialect:
- **Statement Restriction**: Only a single `SELECT` statement (or approved read-only CTE) is permitted. Multi-statement queries (separated by semicolons) and write operations (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE`, `GRANT`, `COPY`, `VACUUM`) are strictly rejected.
- **Schema & CTE Isolation**: Rejects system schemas (`pg_catalog`, `information_schema`, `pg_temp`, `pg_toast`), table-valued functions, and data-modifying CTEs (`WITH x AS (DELETE ...)`).
- **Prohibited Functions**: Rejects dangerous system functions including `pg_sleep`, `set_config`, `current_setting`, `dblink`, `lo_import`, `lo_export`, and administrative lock functions.
- **Strict Row Bounds**: Automatically verifies or injects a strict `LIMIT` clause bounded by `MAX_RESULT_ROWS` (default: 100).
- **No Wildcard Expansions**: Prohibits unqualified `SELECT *` statements (except inside `COUNT(*)` aggregations) to ensure explicit column selection.

### Dual Database Role Architecture

Security is enforced at the database engine level in addition to application-level code:

| Property | Owner Role (`querypilot`) | Read-Only Role (`querypilot_ro`) |
| :--- | :--- | :--- |
| **Primary Responsibility** | Schema migrations, seeding, application metadata, checkpoints | Executing validated generated SQL queries |
| **Transaction Access** | Read / Write | `default_transaction_read_only = on` |
| **Statement Timeout** | Default PostgreSQL setting | Hard enforced `statement_timeout = '5000ms'` |
| **Session Timezone** | `UTC` | `UTC` |
| **Table Grants** | Full ownership of all tables | Specific `SELECT` permissions on domain tables only |
| **Metadata Access** | Read/write access to `query_runs` and `alembic_version` | Zero permissions (access denied) |

### PII Protection and Schema Isolation

- **Column-Level Restriction**: The `customers.email` field contains Sensitive Personally Identifiable Information (PII). The PostgreSQL `querypilot_ro` role is explicitly granted column-level access to `customers(id, name, city, created_at)` only. Any attempt to select `email` triggers a database permission denial.
- **Metadata Protection**: Application audit tables (`query_runs`), migration tracking (`alembic_version`), and LangGraph internal state tables are shielded from the read-only role.

---

## Clarification and Ambiguity Engine

Business analytics queries frequently suffer from lexical ambiguity. QueryPilot handles this explicitly:

1. **Intent Extraction**: The user's prompt is parsed into a structured Pydantic intent schema defining target entities, metrics, time windows, filter predicates, and grouping rules.
2. **Ambiguity Triggers**:
   - Vague evaluation terms (e.g., "top", "best", "performing") without an explicit metric trigger a choice between `Revenue`, `Units Sold`, and `Profit`.
   - Relative questions lacking time context trigger temporal clarification (`Last 30 Days`, `Previous Calendar Month`, `All Time`).
   - Ambiguity between registered users and purchasing customers prompts entity clarification.
3. **LangGraph Interrupt/Resume Workflow**: When clarification is needed, the engine issues a LangGraph `interrupt()`, recording the pending options and query ID.
4. **State Re-evaluation**: Once the user submits their choice via the `/clarify` endpoint, execution resumes using the persistent thread ID, reapplies the chosen parameters, and proceeds to schema retrieval.

---

## Database Domain and Business Semantics

The database schema models a standard retail e-commerce platform:

```
 customers                       orders
+-------------+                 +------------------+
| id (PK)     |<---+            | id (PK)          |<---+
| name        |    |            | customer_id (FK) |--+ |
| email [PII] |    +------------| order_date       |  | |
| city        |                 | status           |  | |
| created_at  |                 | total_amount     |  | |
+-------------+                 +------------------+  | |
                                                      | |
 products                       order_items           | |
+-------------+                 +------------------+  | |
| id (PK)     |<---+            | id (PK)          |  | |
| name        |    |            | order_id (FK)    |--+ |
| category    |    +------------| product_id (FK)  |----+
| cost_price  |                 | quantity         |
+-------------+                 | unit_price       |
                                +------------------+
```

### Business Metric Definitions

- **Completed Orders Only**: Calculations for revenue, units sold, and profit exclusively include orders with `status IN ('completed', 'shipped')`. Records marked `pending`, `cancelled`, or `refunded` are excluded.
- **Gross Revenue**: `SUM(order_items.quantity * order_items.unit_price)`
- **Units Sold**: `SUM(order_items.quantity)`
- **Gross Profit**: `SUM(order_items.quantity * (order_items.unit_price - products.cost_price))`
- **Cost Model**: Profit calculations reference current `products.cost_price` (historical cost variance is not modeled in the current schema version).
- **Temporal Handling**: All timestamps are stored as `timestamptz` with a mandatory UTC timezone policy.

---

## Project Directory Layout

```
QueryPilot/
|-- app/
|   |-- api/                       # API routers and request/response schemas (Phase 5)
|   |-- core/
|   |   |-- config.py              # Pydantic Settings configuration loader
|   |   |-- exceptions.py          # Structured domain exception hierarchy
|   |   |-- logging.py             # Structlog configuration (ISO timestamps, contextvars)
|   |   `-- policy.py              # Security policy: table/column allowlists and rules
|   |-- db/
|   |   |-- engine.py              # Dual database engine factories (owner vs. read-only)
|   |   |-- models.py              # SQLAlchemy 2.x declarative ORM models
|   |   `-- seed.py                # Deterministic database seeding script
|   |-- graph/                     # LangGraph workflow nodes, state, and edges (Phase 4)
|   |-- llm/                       # Provider factory, mock provider, prompts (Phase 3)
|   `-- services/                  # Validation, execution, retrieval, and explanation
|-- docs/
|   |-- decisions.md               # Architectural Decisions Log
|   `-- SPEC.md                    # Canonical project engineering specification
|-- migrations/
|   |-- env.py                     # Alembic migration environment
|   `-- versions/
|       `-- 0001_initial.py        # Initial DDL migration and read-only role provisioning
|-- scripts/
|   `-- verify_readonly.py         # Standalone read-only role verification script
|-- tests/
|   `-- integration/
|       `-- test_phase1_db.py      # Database and permissions integration test suite
|-- docker-compose.yml             # Local PostgreSQL 16 container definition
|-- pyproject.toml                 # Project metadata and pinned dependencies
|-- uv.lock                        # Pinned lockfile generated via uv
`-- .env.example                   # Environment variable template
```

---

## Environment Configuration

Configuration is managed via environment variables and loaded through `pydantic-settings`. Create a `.env` file from `.env.example`:

```bash
cp .env.example .env
```

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `DATABASE_URL` | `postgresql+psycopg://querypilot:querypilot_dev@localhost:5432/querypilot` | Connection string for administrative and owner operations |
| `READONLY_DATABASE_URL` | `postgresql+psycopg://querypilot_ro:querypilot_ro_dev@localhost:5432/querypilot` | Connection string for read-only query execution |
| `MOCK_MODE` | `true` | When true, executes offline without external LLM API calls |
| `LLM_PROVIDER` | `openai` | Active provider (`openai` or `anthropic`) |
| `LLM_MODEL` | `gpt-4o-mini` | Target model name |
| `LLM_API_KEY` | `""` | Provider API key (optional when `MOCK_MODE=true`) |
| `LLM_TEMPERATURE` | `0.0` | Sampling temperature for intent and SQL generation |
| `LLM_TIMEOUT_SECONDS`| `30` | Network timeout for LLM provider requests |
| `MAX_SQL_RETRIES` | `2` | Maximum retry attempts for recoverable SQL errors |
| `MAX_CLARIFICATION_ROUNDS` | `3` | Maximum conversational clarification turns |
| `MAX_RESULT_ROWS` | `100` | Upper limit on rows returned by generated queries |
| `SQL_STATEMENT_TIMEOUT_MS`| `5000` | Statement execution timeout in milliseconds |
| `LOG_LEVEL` | `INFO` | Application log verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

---

## Local Setup and Installation

### Prerequisites

- Python 3.12 or higher (Python 3.13 supported)
- [uv](https://github.com/astral-sh/uv) (recommended Python package manager) or standard `pip`
- Docker and Docker Compose

### 1. Clone Repository and Synchronize Dependencies

```bash
git clone https://github.com/RaunakSachdeva2004/QueryPilot---A-text-to-SQL-tool.git
cd "QueryPilot - A text to SQL tool"

# Synchronize virtual environment using uv
uv sync
```

### 2. Launch PostgreSQL Container

Start the PostgreSQL 16 Alpine container:

```bash
docker compose up -d
```

Verify that the database container is healthy:

```bash
docker compose ps
```

### 3. Apply Database Migrations

Run Alembic to create domain tables (`customers`, `products`, `orders`, `order_items`), application audit tables (`query_runs`), and configure the `querypilot_ro` database role:

```bash
uv run alembic upgrade head
```

### 4. Seed Deterministic Sample Data

Populate the database with deterministic data for testing aggregations, date windows, and join paths:

```bash
uv run python -m app.db.seed
```

---

## Verification and Testing

### Read-Only Security Verification Script

Execute the standalone security verification suite to confirm that database-level restrictions are enforced on the `querypilot_ro` role:

```bash
uv run python scripts/verify_readonly.py
```

Expected output:
```
======================================================================
READ-ONLY ROLE VERIFICATION RESULTS
======================================================================
  [PASS] [ALLOW] SELECT allowed columns from customers
  [PASS] [ALLOW] SELECT from products
  [PASS] [ALLOW] SELECT from orders
  [PASS] [ALLOW] SELECT from order_items
  [PASS] [DENY] SELECT customers.email (PII) (correctly denied)
  [PASS] [DENY] INSERT into customers (correctly denied)
  [PASS] [DENY] UPDATE customers (correctly denied)
  [PASS] [DENY] DELETE from customers (correctly denied)
  [PASS] [DENY] SELECT from query_runs (correctly denied)
  [PASS] [DENY] SELECT from alembic_version (correctly denied)
  [PASS] [DENY] DROP TABLE (correctly denied)
  [PASS] [DENY] CREATE TABLE (correctly denied)
======================================================================
ALL CHECKS PASSED [OK]
```

### Automated Integration Test Suite

Run integration tests using pytest:

```bash
uv run pytest tests/ -v
```

Execution verifies:
- Read-only role execution on authorized customer columns
- Read-only selection on products, orders, and order items
- Permission denial on `customers.email` (PII protection)
- Blocked mutation operations (`INSERT`)
- Access denial on internal metadata tables (`query_runs`, `alembic_version`)

---

## Implementation Roadmap

The project is structured across six sequential engineering phases:

- [X] **Phase 1: Project Foundation**
  - Dependency management (`pyproject.toml`, `uv.lock`)
  - Application settings (`pydantic-settings`) and logging (`structlog`)
  - Domain models (SQLAlchemy 2.x) and Alembic migrations
  - PostgreSQL dual-role separation and column-level grants
  - Deterministic seed script and security verification suite
- [ ] **Phase 2: Safety Core**
  - Abstract Syntax Tree SQL validator (`sqlglot`)
  - Parameterized and bounded SQL executor
  - Sanitized error transformations
  - SQLSTATE-based retryability classification
  - Comprehensive unit and security test suites
- [ ] **Phase 3: Retrieval and LLM Adapter Layer**
  - Schema introspection with TTL cache
  - Relationship traversal and keyword retrieval
  - Business glossary definitions
  - LLM provider factory (OpenAI, Anthropic) and deterministic Mock Provider
  - Structured prompt templates
- [ ] **Phase 4: Workflow Orchestration Engine**
  - Pydantic intent parsing models
  - Ambiguity detection rules
  - LangGraph state graph with `interrupt()` and `resume()`
  - PostgreSQL persistent checkpointer (`AsyncPostgresSaver`)
  - Bounded error correction loop
- [ ] **Phase 5: API Layer and Demonstration Interface**
  - FastAPI endpoints (`/api/v1/query`, `/api/v1/query/{query_id}/clarify`, `/api/v1/health`, `/api/v1/schema`)
  - Execution metadata persistence in `query_runs`
  - Interactive Streamlit demonstration interface
- [ ] **Phase 6: Evaluation and Benchmarks**
  - Benchmark suite featuring 20+ realistic business queries
  - Accuracy and latency metrics runner
  - Final project documentation and technical summary

---

## Platform and Compatibility Notes

- **Windows Async Event Loop**: The default Windows asyncio event loop has known limitations with `psycopg` asynchronous connection pools. In a Windows production setup, run the FastAPI application within Docker or Windows Subsystem for Linux (WSL2). Synchronous operations (Alembic migrations, seed script, and CLI verification scripts) execute natively on Windows without issues.
- **PostgreSQL Version**: Requires PostgreSQL 16+ to support modern role-level configuration options and SQLGlot PostgreSQL dialect features.
- **Python Version**: Tested with Python 3.12 and Python 3.13.