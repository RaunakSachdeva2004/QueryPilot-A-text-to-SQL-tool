"""
Deterministic seed script for the QueryPilot e-commerce database.

Uses a seeded RNG so data is reproducible. Dates are relative to seed time
so relative-date questions (e.g. "last 30 days") return data.
Some customers never place orders (to distinguish registered vs purchasing).

Run:  python -m app.db.seed
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.db.engine import get_owner_engine
from app.db.models import Base, Customer, Order, OrderItem, Product

# ── Constants ───────────────────────────────────────────────

SEED = 42
RNG = random.Random(SEED)

CATEGORIES = ["Electronics", "Clothing", "Books", "Home & Garden", "Sports"]
CITIES = ["New York", "San Francisco", "Chicago", "Austin", "Seattle", "Denver", "Miami", "Boston"]

PRODUCT_DATA = [
    ("Wireless Headphones", "Electronics", 25.00),
    ("USB-C Hub", "Electronics", 12.50),
    ("Mechanical Keyboard", "Electronics", 35.00),
    ("Running Shoes", "Sports", 28.00),
    ("Yoga Mat", "Sports", 8.00),
    ("Water Bottle", "Sports", 3.50),
    ("Python Cookbook", "Books", 15.00),
    ("Data Science Handbook", "Books", 18.00),
    ("Fiction Novel", "Books", 5.00),
    ("Cotton T-Shirt", "Clothing", 4.00),
    ("Denim Jeans", "Clothing", 15.00),
    ("Winter Jacket", "Clothing", 40.00),
    ("LED Desk Lamp", "Home & Garden", 10.00),
    ("Plant Pot Set", "Home & Garden", 6.00),
    ("Throw Blanket", "Home & Garden", 12.00),
]

FIRST_NAMES = [
    "Alice", "Bob", "Carol", "David", "Eva", "Frank", "Grace", "Henry",
    "Ivy", "Jack", "Karen", "Leo", "Mia", "Noah", "Olivia", "Paul",
    "Quinn", "Rachel", "Sam", "Tina",
]
LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia",
    "Miller", "Davis", "Rodriguez", "Martinez",
]

STATUSES = ["pending", "completed", "shipped", "cancelled", "refunded"]
STATUS_WEIGHTS = [0.10, 0.45, 0.30, 0.10, 0.05]


def _seed_time() -> datetime:
    """The reference time for all seed data. Uses current UTC time."""
    return datetime.now(timezone.utc)


def seed_database() -> None:
    """Seed the database with deterministic sample data."""
    engine = get_owner_engine()
    now = _seed_time()

    with Session(engine) as session:
        # Check if already seeded
        if session.query(Customer).first() is not None:
            print("Database already seeded, skipping.")
            return

        # ── Customers ───────────────────────────────────
        customers: list[Customer] = []
        for i in range(20):
            first = FIRST_NAMES[i]
            last = RNG.choice(LAST_NAMES)
            days_ago = RNG.randint(60, 365)
            customer = Customer(
                name=f"{first} {last}",
                email=f"{first.lower()}.{last.lower()}@example.com",
                city=RNG.choice(CITIES),
                created_at=now - timedelta(days=days_ago),
            )
            customers.append(customer)
        session.add_all(customers)
        session.flush()  # Get IDs

        # ── Products ────────────────────────────────────
        products: list[Product] = []
        for name, category, cost in PRODUCT_DATA:
            product = Product(name=name, category=category, cost_price=cost)
            products.append(product)
        session.add_all(products)
        session.flush()

        # ── Orders ──────────────────────────────────────
        # Customers 0..14 place orders; customers 15..19 are "registered but never purchased"
        ordering_customers = customers[:15]
        all_orders: list[Order] = []

        for _ in range(50):
            customer = RNG.choice(ordering_customers)
            days_ago = RNG.randint(1, 90)  # orders in the last 90 days
            status = RNG.choices(STATUSES, weights=STATUS_WEIGHTS, k=1)[0]

            # Pick 1-4 items for this order
            num_items = RNG.randint(1, 4)
            chosen_products = RNG.sample(products, min(num_items, len(products)))

            items: list[OrderItem] = []
            total = 0.0
            for prod in chosen_products:
                qty = RNG.randint(1, 5)
                # unit_price has a markup over cost_price
                markup = RNG.uniform(1.3, 2.5)
                unit_price = round(float(prod.cost_price) * markup, 2)
                total += qty * unit_price
                items.append(
                    OrderItem(
                        product=prod,
                        quantity=qty,
                        unit_price=unit_price,
                    )
                )

            order = Order(
                customer=customer,
                order_date=now - timedelta(days=days_ago, hours=RNG.randint(0, 23)),
                status=status,
                total_amount=round(total, 2),
            )
            order.items = items
            all_orders.append(order)

        session.add_all(all_orders)
        session.commit()

        print(f"Seeded: {len(customers)} customers, {len(products)} products, "
              f"{len(all_orders)} orders")
        # Summary stats
        completed = sum(1 for o in all_orders if o.status in ("completed", "shipped"))
        never_ordered = len(customers) - len(ordering_customers)
        print(f"  Completed/shipped orders: {completed}")
        print(f"  Customers who never ordered: {never_ordered}")


if __name__ == "__main__":
    seed_database()
