"""
Phase 1 verification: prove that the read-only role is properly restricted.

Tests that the querypilot_ro role:
  1. Can SELECT allowed columns from domain tables
  2. CANNOT SELECT customers.email (column-level restriction)
  3. CANNOT INSERT/UPDATE/DELETE (read-only role)
  4. CANNOT read query_runs (no grant)
  5. CANNOT read alembic_version (no grant)

Run: python scripts/verify_readonly.py
"""
from __future__ import annotations

import sys

from sqlalchemy import create_engine, text

from app.core.config import get_settings


def main() -> None:
    settings = get_settings()
    ro_engine = create_engine(settings.readonly_database_url)
    owner_engine = create_engine(settings.database_url)

    results: list[tuple[str, bool, str]] = []

    def check(name: str, fn) -> None:
        try:
            fn()
            results.append((name, True, "OK"))
        except Exception as e:
            results.append((name, False, str(e)[:200]))

    def should_succeed(name: str, fn) -> None:
        check(f"[ALLOW] {name}", fn)

    def should_fail(name: str, fn) -> None:
        try:
            fn()
            results.append((f"[DENY] {name}", False, "EXPECTED FAILURE but succeeded"))
        except Exception as e:
            results.append((f"[DENY] {name} (correctly denied)", True, str(e)[:200]))

    # ── Tests that SHOULD succeed ───────────────────────────

    def test_select_customers_allowed():
        with ro_engine.connect() as conn:
            rows = conn.execute(text("SELECT id, name, city FROM customers LIMIT 1")).fetchall()
            assert len(rows) >= 0

    def test_select_products():
        with ro_engine.connect() as conn:
            rows = conn.execute(text("SELECT id, name, category, cost_price FROM products LIMIT 1")).fetchall()
            assert len(rows) >= 0

    def test_select_orders():
        with ro_engine.connect() as conn:
            rows = conn.execute(text("SELECT id, customer_id, order_date, status, total_amount FROM orders LIMIT 1")).fetchall()
            assert len(rows) >= 0

    def test_select_order_items():
        with ro_engine.connect() as conn:
            rows = conn.execute(text("SELECT id, order_id, product_id, quantity, unit_price FROM order_items LIMIT 1")).fetchall()
            assert len(rows) >= 0

    should_succeed("SELECT allowed columns from customers", test_select_customers_allowed)
    should_succeed("SELECT from products", test_select_products)
    should_succeed("SELECT from orders", test_select_orders)
    should_succeed("SELECT from order_items", test_select_order_items)

    # ── Tests that SHOULD fail ──────────────────────────────

    def test_select_email():
        with ro_engine.connect() as conn:
            conn.execute(text("SELECT email FROM customers LIMIT 1")).fetchall()

    def test_insert():
        with ro_engine.connect() as conn:
            conn.execute(text("INSERT INTO customers (name, email, city) VALUES ('x', 'x@x.com', 'X')"))
            conn.commit()

    def test_update():
        with ro_engine.connect() as conn:
            conn.execute(text("UPDATE customers SET name = 'hacked' WHERE id = 1"))
            conn.commit()

    def test_delete():
        with ro_engine.connect() as conn:
            conn.execute(text("DELETE FROM customers WHERE id = 1"))
            conn.commit()

    def test_select_query_runs():
        with ro_engine.connect() as conn:
            conn.execute(text("SELECT * FROM query_runs LIMIT 1")).fetchall()

    def test_select_alembic_version():
        with ro_engine.connect() as conn:
            conn.execute(text("SELECT * FROM alembic_version")).fetchall()

    def test_drop_table():
        with ro_engine.connect() as conn:
            conn.execute(text("DROP TABLE customers"))
            conn.commit()

    def test_create_table():
        with ro_engine.connect() as conn:
            conn.execute(text("CREATE TABLE hacked (id int)"))
            conn.commit()

    should_fail("SELECT customers.email (PII)", test_select_email)
    should_fail("INSERT into customers", test_insert)
    should_fail("UPDATE customers", test_update)
    should_fail("DELETE from customers", test_delete)
    should_fail("SELECT from query_runs", test_select_query_runs)
    should_fail("SELECT from alembic_version", test_select_alembic_version)
    should_fail("DROP TABLE", test_drop_table)
    should_fail("CREATE TABLE", test_create_table)

    # ── Report ──────────────────────────────────────────────

    print("\n" + "=" * 70)
    print("READ-ONLY ROLE VERIFICATION RESULTS")
    print("=" * 70)
    all_passed = True
    for name, passed, detail in results:
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_passed = False
        print(f"  [{status}] {name}")
        if not passed:
            print(f"         {detail}")

    print("=" * 70)
    if all_passed:
        print("ALL CHECKS PASSED [OK]")
    else:
        print("SOME CHECKS FAILED [FAIL]")
        sys.exit(1)


if __name__ == "__main__":
    main()
