"""
Seed the demo SQLite database with our SaaS schema + realistic sample data.

Run this once to set up the demo:
    python scripts/seed_database.py

Creates data/demo.db with 7 tables and ~100-300 rows each.
The data is designed to create ambiguity scenarios for the clarification engine.
"""

import sqlite3
import random
import os
from datetime import datetime, timedelta
from pathlib import Path

# make sure the data directory exists
DB_PATH = Path(__file__).parent.parent / "data" / "demo.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# nuke any old database so we start fresh
if DB_PATH.exists():
    DB_PATH.unlink()


# ----- schema -----

SCHEMA_SQL = """
-- the core customer table
CREATE TABLE customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    company TEXT,
    plan_type TEXT CHECK(plan_type IN ('free', 'starter', 'pro', 'enterprise')),
    signup_date DATE NOT NULL,
    country TEXT
);

-- subscription details — where MRR lives
CREATE TABLE subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    plan_name TEXT NOT NULL,
    monthly_fee DECIMAL(10,2) NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('active', 'cancelled', 'trial', 'paused')),
    start_date DATE NOT NULL,
    end_date DATE
);

-- financial records
CREATE TABLE invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscription_id INTEGER NOT NULL REFERENCES subscriptions(id),
    amount DECIMAL(10,2) NOT NULL,
    tax DECIMAL(10,2) DEFAULT 0,
    discount DECIMAL(10,2) DEFAULT 0,
    payment_status TEXT CHECK(payment_status IN ('paid', 'pending', 'overdue', 'refunded')),
    issued_date DATE NOT NULL,
    paid_date DATE
);

-- customer support tracking
CREATE TABLE support_tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    subject TEXT NOT NULL,
    priority TEXT CHECK(priority IN ('low', 'medium', 'high', 'critical')),
    status TEXT CHECK(status IN ('open', 'in_progress', 'resolved', 'closed')),
    created_at TIMESTAMP NOT NULL,
    resolved_at TIMESTAMP
);

-- what we sell
CREATE TABLE products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT,
    base_price DECIMAL(10,2),
    description TEXT
);

-- usage/activity tracking
CREATE TABLE usage_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    event_type TEXT CHECK(event_type IN ('page_view', 'api_call', 'export', 'login')),
    quantity INTEGER DEFAULT 1,
    timestamp TIMESTAMP NOT NULL
);

-- internal team — intentionally creates name ambiguity with customers
CREATE TABLE employees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    department TEXT CHECK(department IN ('engineering', 'sales', 'support', 'marketing')),
    role TEXT
);
"""

# ----- sample data generators -----

# some names that overlap between customers and employees (for ambiguity)
SHARED_NAMES = ["Jack Wilson", "Sarah Chen", "Alex Kumar"]

CUSTOMER_NAMES = [
    *SHARED_NAMES,
    "Emma Thompson", "Liam Rodriguez", "Olivia Patel", "Noah Kim",
    "Ava Nakamura", "William Santos", "Sophia Andersson", "James O'Brien",
    "Isabella Garcia", "Benjamin Park", "Mia Johansson", "Lucas Weber",
    "Charlotte Müller", "Henry Dubois", "Amelia Costa", "Daniel Tanaka",
    "Harper Singh", "Michael Brown", "Evelyn Zhang", "David Kowalski",
    "Luna Martinez", "Ethan Yamamoto", "Aria Fernandez", "Sebastian Lee",
    "Chloe Wang", "Owen Taylor", "Penelope Reyes", "Alexander Ivanov",
    "Layla Petrov", "Samuel Okafor", "Riley Sato", "Joseph Lindgren",
    "Zoey Moreau", "Jackson Fischer", "Nora Bergström", "Aiden Al-Rashid",
    "Lily Nakamura", "Carter Wright", "Eleanor Rossi", "Jayden Thorne",
    "Hannah O'Connor", "Wyatt Hoffman", "Addison Steele", "Luke Vargas",
    "Stella Beaumont", "Gabriel Ortiz", "Aurora Lindqvist", "Julian Hayes",
    "Savannah Novak", "Mateo Engström",
]

COMPANIES = [
    "Acme Corp", "TechFlow Inc", "DataWave", "CloudNine Solutions",
    "Nexus Analytics", "Bright Pixel", "Summit Digital", "StreamLine Co",
    "Quantum Labs", "Forge Systems", "Apex Technologies", "Nova Metrics",
    "Zenith Platforms", "Pulse Software", "Horizon AI", "ClearPath Data",
    "BlueSky Ops", "Vertex Solutions", "Prism Analytics", "Catalyst Hub",
    None, None, None,  # some customers don't have a company
]

COUNTRIES = [
    "US", "US", "US", "US",  # weighted towards US
    "UK", "UK", "Canada", "Germany", "France",
    "Japan", "India", "Brazil", "Australia", "Sweden",
    "South Korea", "Netherlands", "Singapore", "Mexico",
]

PLAN_TYPES = ["free", "starter", "pro", "enterprise"]
PLAN_PRICES = {"free": 0, "starter": 29, "pro": 99, "enterprise": 299}

EMPLOYEE_NAMES = [
    *SHARED_NAMES,  # same names as some customers — this is the ambiguity
    "Rachel Torres", "Kevin Nguyen", "Monica Stahl", "Tom Bradley",
    "Jessica Liu", "Ryan Mitchell", "Amanda Foster", "Chris DeMarco",
    "Priya Sharma", "Marcus Johnson", "Elena Volkov", "Derek Chang",
]

DEPARTMENTS = ["engineering", "sales", "support", "marketing"]
ROLES = {
    "engineering": ["engineer", "senior engineer", "tech lead", "manager"],
    "sales": ["account exec", "sales rep", "manager", "director"],
    "support": ["support agent", "senior agent", "manager"],
    "marketing": ["analyst", "content lead", "manager", "director"],
}

PRODUCTS = [
    ("SQLPilot Core", "analytics", 0, "Core text-to-SQL engine"),
    ("SQLPilot Pro", "analytics", 99, "Advanced features + priority support"),
    ("Data Connector", "integration", 49, "Connect to external data sources"),
    ("Dashboard Builder", "visualization", 79, "Drag-and-drop dashboard creation"),
    ("API Gateway", "infrastructure", 149, "Managed API gateway for data access"),
]

TICKET_SUBJECTS = [
    "Can't connect to database",
    "Query returning wrong results",
    "Dashboard not loading",
    "Need help with complex join",
    "Billing question",
    "Feature request: export to CSV",
    "Performance issue with large tables",
    "How to set up SSO?",
    "API rate limiting concern",
    "Data sync not working",
    "Need to upgrade plan",
    "Column mapping is incorrect",
    "Timeout on aggregation query",
    "Permission denied error",
    "Request for custom integration",
]


def random_date(start_year=2023, end_year=2026):
    """generate a random date between start_year and end_year."""
    start = datetime(start_year, 1, 1)
    end = datetime(end_year, 9, 1)
    delta = end - start
    random_days = random.randint(0, delta.days)
    return (start + timedelta(days=random_days)).strftime("%Y-%m-%d")


def random_timestamp(base_date_str):
    """slap a random time onto a date string."""
    hour = random.randint(0, 23)
    minute = random.randint(0, 59)
    second = random.randint(0, 59)
    return f"{base_date_str} {hour:02d}:{minute:02d}:{second:02d}"


def seed_database():
    """create and populate the demo database."""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    # foreign keys are off by default in sqlite, turn them on
    cursor.execute("PRAGMA foreign_keys = ON;")

    # create all tables
    cursor.executescript(SCHEMA_SQL)

    # --- seed customers ---
    customers = []
    for i, name in enumerate(CUSTOMER_NAMES):
        plan = random.choice(PLAN_TYPES)
        company = random.choice(COMPANIES)
        country = random.choice(COUNTRIES)
        signup = random_date(2023, 2026)
        # make email from name
        email = name.lower().replace(" ", ".").replace("'", "") + f"@{(company or 'gmail').lower().replace(' ', '')}.com"

        cursor.execute(
            "INSERT INTO customers (name, email, company, plan_type, signup_date, country) VALUES (?, ?, ?, ?, ?, ?)",
            (name, email, company, plan, signup, country),
        )
        customers.append({"id": i + 1, "plan": plan, "signup": signup})

    # --- seed subscriptions ---
    # each customer gets 1-2 subscriptions (some upgraded/downgraded)
    sub_id = 0
    subscriptions = []
    for cust in customers:
        num_subs = random.choices([1, 2], weights=[70, 30])[0]
        for j in range(num_subs):
            plan = cust["plan"] if j == 0 else random.choice(PLAN_TYPES)
            fee = PLAN_PRICES[plan] + random.uniform(-5, 10)  # slight variation
            fee = round(max(fee, 0), 2)

            # most are active, some cancelled/trial/paused
            if j == 0:
                status = random.choices(
                    ["active", "cancelled", "trial", "paused"],
                    weights=[60, 15, 15, 10],
                )[0]
            else:
                # older subscription is probably cancelled
                status = random.choices(
                    ["cancelled", "active", "paused"],
                    weights=[60, 25, 15],
                )[0]

            start = cust["signup"] if j == 0 else random_date(2023, 2024)
            end_date = None
            if status == "cancelled":
                # ended sometime after start
                start_dt = datetime.strptime(start, "%Y-%m-%d")
                end_dt = start_dt + timedelta(days=random.randint(30, 365))
                end_date = end_dt.strftime("%Y-%m-%d")

            sub_id += 1
            cursor.execute(
                "INSERT INTO subscriptions (customer_id, plan_name, monthly_fee, status, start_date, end_date) VALUES (?, ?, ?, ?, ?, ?)",
                (cust["id"], plan, fee, status, start, end_date),
            )
            subscriptions.append({"id": sub_id, "customer_id": cust["id"], "fee": fee, "start": start})

    # --- seed invoices ---
    # each subscription gets 1-12 monthly invoices
    for sub in subscriptions:
        num_invoices = random.randint(1, 12)
        start_dt = datetime.strptime(sub["start"], "%Y-%m-%d")

        for month_offset in range(num_invoices):
            invoice_date = start_dt + timedelta(days=30 * month_offset)
            if invoice_date > datetime(2026, 9, 1):
                break

            amount = sub["fee"]
            tax = round(amount * random.uniform(0.05, 0.15), 2)
            # occasional discount
            discount = round(amount * random.uniform(0, 0.2), 2) if random.random() < 0.2 else 0

            payment_status = random.choices(
                ["paid", "pending", "overdue", "refunded"],
                weights=[70, 15, 10, 5],
            )[0]

            paid_date = None
            issued = invoice_date.strftime("%Y-%m-%d")
            if payment_status == "paid":
                # paid within 1-30 days of issue
                paid_dt = invoice_date + timedelta(days=random.randint(0, 30))
                paid_date = paid_dt.strftime("%Y-%m-%d")

            cursor.execute(
                "INSERT INTO invoices (subscription_id, amount, tax, discount, payment_status, issued_date, paid_date) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (sub["id"], amount, tax, discount, payment_status, issued, paid_date),
            )

    # --- seed products ---
    product_ids = []
    for name, category, price, desc in PRODUCTS:
        cursor.execute(
            "INSERT INTO products (name, category, base_price, description) VALUES (?, ?, ?, ?)",
            (name, category, price, desc),
        )
        product_ids.append(cursor.lastrowid)

    # --- seed usage_events ---
    # each customer gets 5-50 usage events
    for cust in customers:
        num_events = random.randint(5, 50)
        for _ in range(num_events):
            product_id = random.choice(product_ids)
            event_type = random.choice(["page_view", "api_call", "export", "login"])
            quantity = random.randint(1, 10) if event_type == "api_call" else 1
            ts = random_timestamp(random_date(2024, 2026))

            cursor.execute(
                "INSERT INTO usage_events (customer_id, product_id, event_type, quantity, timestamp) VALUES (?, ?, ?, ?, ?)",
                (cust["id"], product_id, event_type, quantity, ts),
            )

    # --- seed support_tickets ---
    # roughly 60% of customers have filed tickets
    for cust in customers:
        if random.random() > 0.6:
            continue
        num_tickets = random.randint(1, 5)
        for _ in range(num_tickets):
            subject = random.choice(TICKET_SUBJECTS)
            priority = random.choices(
                ["low", "medium", "high", "critical"],
                weights=[30, 40, 20, 10],
            )[0]
            status = random.choices(
                ["open", "in_progress", "resolved", "closed"],
                weights=[15, 15, 40, 30],
            )[0]

            created = random_timestamp(random_date(2024, 2026))
            resolved = None
            if status in ("resolved", "closed"):
                # resolved 1-14 days after creation
                created_dt = datetime.strptime(created, "%Y-%m-%d %H:%M:%S")
                resolved_dt = created_dt + timedelta(
                    hours=random.randint(1, 336)  # 1 hour to 14 days
                )
                resolved = resolved_dt.strftime("%Y-%m-%d %H:%M:%S")

            cursor.execute(
                "INSERT INTO support_tickets (customer_id, subject, priority, status, created_at, resolved_at) VALUES (?, ?, ?, ?, ?, ?)",
                (cust["id"], subject, priority, status, created, resolved),
            )

    # --- seed employees ---
    for name in EMPLOYEE_NAMES:
        dept = random.choice(DEPARTMENTS)
        role = random.choice(ROLES[dept])
        cursor.execute(
            "INSERT INTO employees (name, department, role) VALUES (?, ?, ?)",
            (name, dept, role),
        )

    conn.commit()

    # print some stats so we know it worked
    tables = ["customers", "subscriptions", "invoices", "support_tickets", "products", "usage_events", "employees"]
    print(f"\n[OK] Demo database created at: {DB_PATH}")
    print("-" * 40)
    for table in tables:
        count = cursor.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {count} rows")

    conn.close()


if __name__ == "__main__":
    random.seed(42)  # reproducible data
    seed_database()
