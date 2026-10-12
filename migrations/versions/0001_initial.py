"""Initial schema, query_runs, and read-only role

Revision ID: 0001_initial
Revises: None
Create Date: 2024-01-01 00:00:00.000000

Creates:
  - customers, products, orders, order_items tables (e-commerce domain)
  - query_runs table (application metadata)
  - querypilot_ro role with:
      SELECT-only on domain tables
      Column-level grant EXCLUDING customers.email
      NO access to query_runs, alembic_version, checkpoint tables
      default_transaction_read_only = on
      statement_timeout = 5000ms
      timezone = UTC
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers
revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Domain tables ───────────────────────────────────────

    op.create_table(
        "customers",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "products",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("cost_price", sa.Numeric(10, 2), nullable=False),
    )

    op.create_table(
        "orders",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "customer_id",
            sa.Integer,
            sa.ForeignKey("customers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("order_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=False),
    )
    op.create_index("ix_orders_customer_id", "orders", ["customer_id"])
    op.create_index("ix_orders_status", "orders", ["status"])
    op.create_index("ix_orders_order_date", "orders", ["order_date"])

    op.create_table(
        "order_items",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "order_id",
            sa.Integer,
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            sa.Integer,
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("unit_price", sa.Numeric(10, 2), nullable=False),
    )
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])
    op.create_index("ix_order_items_product_id", "order_items", ["product_id"])

    # ── Application metadata table ──────────────────────────

    op.create_table(
        "query_runs",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("conversation_id", UUID(as_uuid=False), nullable=True, index=True),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("mode", sa.String(10), nullable=False, server_default="mock"),
        sa.Column("generated_sql", sa.Text, nullable=True),
        sa.Column("result_columns", sa.Text, nullable=True),
        sa.Column("result_rows", sa.Text, nullable=True),
        sa.Column("explanation", sa.Text, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("clarification_question", sa.Text, nullable=True),
        sa.Column("clarification_options", sa.Text, nullable=True),
        sa.Column("execution_duration_ms", sa.Integer, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # ── Read-only role ──────────────────────────────────────
    # Uses raw SQL because Alembic/SQLAlchemy don't have DDL for roles/grants.

    op.execute("""
        DO $$
        BEGIN
            -- Create role if it doesn't exist
            IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'querypilot_ro') THEN
                CREATE ROLE querypilot_ro WITH LOGIN PASSWORD 'querypilot_ro_dev';
            END IF;
        END
        $$;
    """)

    # Role-level settings
    op.execute("ALTER ROLE querypilot_ro SET default_transaction_read_only = on;")
    op.execute("ALTER ROLE querypilot_ro SET statement_timeout = '5000ms';")
    op.execute("ALTER ROLE querypilot_ro SET timezone = 'UTC';")

    # Grant CONNECT on database (needed to log in)
    op.execute("GRANT CONNECT ON DATABASE querypilot TO querypilot_ro;")

    # Grant USAGE on public schema
    op.execute("GRANT USAGE ON SCHEMA public TO querypilot_ro;")

    # ── Column-level grants for customers (exclude email) ──
    op.execute("""
        GRANT SELECT (id, name, city, created_at) ON customers TO querypilot_ro;
    """)

    # ── Full SELECT on other domain tables ──────────────────
    op.execute("GRANT SELECT ON products TO querypilot_ro;")
    op.execute("GRANT SELECT ON orders TO querypilot_ro;")
    op.execute("GRANT SELECT ON order_items TO querypilot_ro;")

    # NOTE: No grants on query_runs, alembic_version, or checkpoint tables.
    # The read-only role cannot see application metadata.

    # Also set timezone on the owner role for consistency
    op.execute("ALTER ROLE querypilot SET timezone = 'UTC';")


def downgrade() -> None:
    # Revoke grants
    op.execute("REVOKE ALL ON customers FROM querypilot_ro;")
    op.execute("REVOKE ALL ON products FROM querypilot_ro;")
    op.execute("REVOKE ALL ON orders FROM querypilot_ro;")
    op.execute("REVOKE ALL ON order_items FROM querypilot_ro;")
    op.execute("REVOKE USAGE ON SCHEMA public FROM querypilot_ro;")
    op.execute("REVOKE CONNECT ON DATABASE querypilot FROM querypilot_ro;")

    # Drop tables in reverse order of creation
    op.drop_table("query_runs")
    op.drop_table("order_items")
    op.drop_table("orders")
    op.drop_table("products")
    op.drop_table("customers")

    # Drop read-only role
    op.execute("DROP ROLE IF EXISTS querypilot_ro;")
