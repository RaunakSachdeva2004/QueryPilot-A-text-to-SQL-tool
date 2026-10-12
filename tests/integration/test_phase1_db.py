"""Integration tests for Phase 1 database foundation and read-only role permissions."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from app.core.config import get_settings


@pytest.fixture(scope="module")
def ro_engine():
    settings = get_settings()
    return create_engine(settings.readonly_database_url)


@pytest.fixture(scope="module")
def owner_engine():
    settings = get_settings()
    return create_engine(settings.database_url)


def test_ro_can_select_allowed_customer_columns(ro_engine):
    with ro_engine.connect() as conn:
        rows = conn.execute(text("SELECT id, name, city FROM customers LIMIT 5")).fetchall()
        assert len(rows) > 0


def test_ro_can_select_products_orders_items(ro_engine):
    with ro_engine.connect() as conn:
        products = conn.execute(text("SELECT id, name, category, cost_price FROM products LIMIT 5")).fetchall()
        orders = conn.execute(text("SELECT id, customer_id, status FROM orders LIMIT 5")).fetchall()
        items = conn.execute(text("SELECT id, order_id, product_id FROM order_items LIMIT 5")).fetchall()
        assert len(products) > 0
        assert len(orders) > 0
        assert len(items) > 0


def test_ro_cannot_select_customer_email(ro_engine):
    with pytest.raises(Exception) as exc_info:
        with ro_engine.connect() as conn:
            conn.execute(text("SELECT email FROM customers LIMIT 1")).fetchall()
    assert "permission denied" in str(exc_info.value).lower()


def test_ro_cannot_insert(ro_engine):
    with pytest.raises(Exception) as exc_info:
        with ro_engine.connect() as conn:
            conn.execute(text("INSERT INTO customers (name, email, city) VALUES ('X', 'x@x.com', 'X')"))
    assert "permission denied" in str(exc_info.value).lower() or "read-only" in str(exc_info.value).lower()


def test_ro_cannot_access_query_runs(ro_engine):
    with pytest.raises(Exception) as exc_info:
        with ro_engine.connect() as conn:
            conn.execute(text("SELECT * FROM query_runs LIMIT 1")).fetchall()
    assert "permission denied" in str(exc_info.value).lower()


def test_ro_cannot_access_alembic_version(ro_engine):
    with pytest.raises(Exception) as exc_info:
        with ro_engine.connect() as conn:
            conn.execute(text("SELECT * FROM alembic_version")).fetchall()
    assert "permission denied" in str(exc_info.value).lower()
