"""Fill the database with realistic, fully fictional data.

Creates the catalogue, customers, orders with timelines, store traffic, the
demo user accounts, notifications, an audit trail and scheduled reports.

Usage: python manage.py seed_demo [--orders 6500] [--months 26]
"""

import bisect
import math
import random
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from dashboard.models import (
    COUNTRIES, AuditLog, Category, Customer, DailyTraffic, Notification, Order, OrderEvent,
    OrderItem, Product, Profile, Region, ScheduledReport,
)
from dashboard.roles import ADMIN, MANAGER, VIEWER, set_role

CATALOG = {
    ("Laptops", "#6366f1"): [
        ("Aero 14 Ultrabook", 1299), ("Forge 16 Pro", 2199), ("Nimbus 13 Air", 999),
        ("Titan 17 Workstation", 2899), ("Pixel Slate 12", 749),
    ],
    ("Monitors", "#0ea5e9"): [
        ("ClearView 27 4K", 449), ("UltraWide 34 Curve", 699), ("Studio 32 HDR", 1099),
        ("Office 24 FHD", 179), ("Gamer 27 240Hz", 529),
    ],
    ("Audio", "#10b981"): [
        ("Pulse ANC Headphones", 299), ("Echo Buds Pro", 179), ("Studio Monitor Pair", 399),
        ("Desk Mic Pro", 149), ("Soundbar Mini", 229),
    ],
    ("Accessories", "#f59e0b"): [
        ("Mechanical Keyboard K8", 129), ("Ergo Mouse M3", 79), ("USB-C Dock 12-in-1", 189),
        ("Laptop Stand Alu", 59), ("4K Webcam", 139), ("Desk Mat XL", 29),
    ],
    ("Storage", "#ec4899"): [
        ("NVMe SSD 2TB", 169), ("Portable SSD 1TB", 119), ("NAS 4-Bay", 549),
        ("microSD 512GB", 49),
    ],
    ("Networking", "#8b5cf6"): [
        ("Mesh Wi-Fi 6E (3-pack)", 449), ("Gigabit Switch 16p", 139), ("Travel Router", 69),
        ("Wi-Fi 7 Router", 399),
    ],
    ("Software", "#14b8a6"): [
        ("Cloud Backup 1yr", 99), ("Security Suite 1yr", 69), ("Office Pro License", 249),
        ("Design Studio 1yr", 359),
    ],
}

FIRST = [
    "Olivia", "Liam", "Emma", "Noah", "Ava", "Lucas", "Sofia", "Mateo", "Mia", "Elias",
    "Hana", "Kenji", "Aisha", "Omar", "Lea", "Jonas", "Chloe", "Arjun", "Priya", "Diego",
    "Valentina", "Yuki", "Sara", "Adam", "Nora", "Felix", "Leila", "Daniel", "Zara", "Ethan",
]
LAST = [
    "Smith", "Müller", "Garcia", "Rossi", "Tanaka", "Khan", "Silva", "Dubois", "Novak", "Kim",
    "Johansson", "Haddad", "Patel", "Costa", "Fischer", "Moreau", "Ito", "Nguyen", "Lopez", "Weber",
]
COMPANY_A = ["Blue", "North", "Bright", "Nova", "Apex", "Quantum", "Silver", "Urban", "Green", "Iron"]
COMPANY_B = ["Labs", "Systems", "Digital", "Works", "Studio", "Logistics", "Retail", "Health", "Media"]

REGION_WEIGHTS = {
    Region.NORTH_AMERICA: 34, Region.EUROPE: 28, Region.ASIA: 20,
    Region.MIDDLE_EAST: 10, Region.LATIN_AMERICA: 8,
}
# Hour-of-day weights: quiet nights, lunch peak, evening peak
HOUR_WEIGHTS = [1, 0.6, 0.4, 0.3, 0.3, 0.5, 1, 2, 3.5, 5, 6, 7, 7.5, 6.5, 5.5, 5, 5, 5.5, 6.5, 8, 8.5, 7, 4.5, 2.5]
CHANNEL_WEIGHTS = {"web": 48, "mobile": 30, "marketplace": 15, "sales": 7}
PAYMENT_WEIGHTS = {"card": 64, "paypal": 26, "bank": 10}

# username, first, last, role, job title, demo account?
TEAM = [
    ("demo", "Alex", "Morgan", ADMIN, "Head of E-commerce", True),
    ("manager", "Jordan", "Lee", MANAGER, "Operations Manager", True),
    ("viewer", "Sam", "Rivera", VIEWER, "Financial Analyst", True),
    ("sara.k", "Sara", "Karimi", ADMIN, "CTO", False),
    ("j.miller", "James", "Miller", MANAGER, "Warehouse Lead", False),
    ("n.tanaka", "Naomi", "Tanaka", MANAGER, "Customer Success", False),
    ("l.dubois", "Lucas", "Dubois", VIEWER, "Marketing Analyst", False),
    ("p.patel", "Priya", "Patel", VIEWER, "Accountant", False),
]


class Command(BaseCommand):
    help = "Delete existing data and generate a fictional demo dataset with demo user accounts."

    def add_arguments(self, parser):
        parser.add_argument("--orders", type=int, default=6500)
        parser.add_argument("--customers", type=int, default=900)
        parser.add_argument("--months", type=int, default=26)
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument(
            "--if-empty", action="store_true",
            help="Do nothing when orders already exist (safe for container start-up).",
        )

    @transaction.atomic
    def handle(self, *args, **opts):
        if opts["if_empty"] and Order.objects.exists():
            self.stdout.write("Data already present, skipping seed.")
            return

        self.rng = random.Random(opts["seed"])
        for model in (Notification, AuditLog, ScheduledReport, OrderEvent, OrderItem, Order,
                      DailyTraffic, Customer, Product, Category):
            model.objects.all().delete()

        self.today = date.today()
        self.start = self.today - timedelta(days=round(opts["months"] * 30.4))
        users = self._create_users()
        products = self._create_catalog()
        customers = self._create_customers(opts["customers"])
        orders = self._create_orders(opts["orders"], customers, products)
        self._create_events(orders, users)
        self._create_traffic()
        self._create_notifications(users, products)
        self._create_audit_trail(users, orders, products)
        self._create_reports(users)

        self.stdout.write(self.style.SUCCESS(
            f"Seeded {len(products)} products, {len(customers)} customers, {len(orders)} orders, "
            f"{OrderItem.objects.count()} line items, {OrderEvent.objects.count()} timeline events, "
            f"{len(users)} users."
        ))
        self.stdout.write(
            f"Demo logins (password '{settings.DEMO_PASSWORD}'): demo (Admin), manager, viewer"
        )

    # ------------------------------------------------------------------ users
    def _create_users(self):
        # Accounts are reset in place rather than recreated, so a daily refresh
        # doesn't sign out visitors who are using the demo at that moment
        User = get_user_model()
        users = {}
        for username, first, last, role, title, is_demo in TEAM:
            user, _ = User.objects.get_or_create(username=username)
            user.email = f"{username.replace('.', '')}@pulse-demo.com"
            user.first_name, user.last_name = first, last
            user.is_active = True
            user.last_login = timezone.now() - timedelta(hours=self.rng.randint(1, 240))
            # Team members are scenery: no password means they can't sign in.
            # Re-hashing an unchanged password would end active sessions, so skip it.
            if is_demo:
                if not user.check_password(settings.DEMO_PASSWORD):
                    user.set_password(settings.DEMO_PASSWORD)
            elif user.has_usable_password():
                user.set_unusable_password()
            user.save()
            Profile.objects.get_or_create(user=user)
            set_role(user, role)
            Profile.objects.filter(user=user).update(
                job_title=title, is_demo=is_demo,
                accent="indigo", currency="USD", timezone="UTC",
            )
            users[username] = user
        return users

    # ---------------------------------------------------------------- catalog
    def _create_catalog(self):
        rng = self.rng
        products = []
        for i, ((cat_name, color), items) in enumerate(CATALOG.items(), start=1):
            category = Category.objects.create(name=cat_name, color=color)
            for j, (name, price) in enumerate(items, start=1):
                margin = rng.uniform(0.18, 0.45) if cat_name != "Software" else rng.uniform(0.7, 0.85)
                reorder = rng.choice([10, 15, 20, 25, 30])
                products.append(Product(
                    name=name,
                    sku=f"{cat_name[:3].upper()}-{i}{j:02d}",
                    category=category,
                    price=Decimal(price),
                    cost=Decimal(str(round(price * (1 - margin), 2))),
                    stock=rng.randint(reorder + 5, 420),
                    reorder_level=reorder,
                ))
        # A few items running low or sold out, so the inventory alerts have something to show
        for p in rng.sample(products, 6):
            p.stock = rng.randint(1, p.reorder_level)
        for p in rng.sample(products, 2):
            p.stock = 0
        return Product.objects.bulk_create(products)

    # -------------------------------------------------------------- customers
    def _create_customers(self, count):
        rng = self.rng
        regions = list(REGION_WEIGHTS)
        weights = list(REGION_WEIGHTS.values())
        span = (self.today - self.start).days
        customers = []
        for i in range(count):
            first, last = rng.choice(FIRST), rng.choice(LAST)
            region = rng.choices(regions, weights)[0]
            countries = COUNTRIES[region]
            is_business = rng.random() < 0.55
            customers.append(Customer(
                name=f"{first} {last}",
                email=f"{first.lower()}.{last.lower().replace('ü', 'u')}{i}@example.com",
                phone=f"+1 555 {rng.randint(100, 999)} {rng.randint(1000, 9999)}",
                company=f"{rng.choice(COMPANY_A)} {rng.choice(COMPANY_B)}" if is_business else "",
                region=region,
                # Earlier countries in each list are the bigger markets
                country=rng.choices(countries, [len(countries) - k + 2 for k in range(len(countries))])[0],
                # Skew sign-ups toward recent months so the customer base keeps growing;
                # the first 60 are existing customers from before the data starts
                joined=self.start + timedelta(
                    days=rng.randint(0, 3) if i < 60 else int(span * rng.random() ** 0.7)),
            ))
        return Customer.objects.bulk_create(customers)

    # ----------------------------------------------------------------- orders
    def _create_orders(self, count, customers, products):
        rng, start, today = self.rng, self.start, self.today
        span = (today - start).days
        # Daily weights: steady growth + Q4 holiday peak + weekly rhythm
        day_weights = []
        for d in range(span + 1):
            day = start + timedelta(days=d)
            growth = 1 + 1.8 * d / span
            season = 1 + 0.45 * math.exp(-((day.timetuple().tm_yday - 335) / 25) ** 2)
            weekday = 0.75 if day.weekday() >= 5 else 1.0
            day_weights.append(growth * season * weekday)
        days = sorted(rng.choices(range(span + 1), day_weights, k=count))

        # Loyal customers come back more often (capped so nobody dominates)
        loyalty = [min(rng.paretovariate(2.2), 8) for _ in customers]
        by_join = sorted(range(len(customers)), key=lambda k: customers[k].joined)
        join_dates = [customers[k].joined for k in by_join]
        orders, pending_items = [], []
        for n, d in enumerate(days, start=1):
            created = start + timedelta(days=d)
            # Only customers who have signed up by this day can order
            joined_count = max(bisect.bisect_right(join_dates, created), 1)
            pool = [by_join[rng.randrange(joined_count)] for _ in range(12)]
            customer = customers[rng.choices(pool, [loyalty[k] for k in pool])[0]]
            age = (today - created).days
            if age < 2:
                status = rng.choice(["pending", "pending", "paid"])
            elif age < 5:
                status = rng.choice(["paid", "shipped", "shipped"])
            elif age < 10:
                status = rng.choice(["shipped", "delivered", "delivered"])
            else:
                status = "refunded" if rng.random() < 0.04 else "delivered"
            hour = rng.choices(range(24), HOUR_WEIGHTS)[0]
            orders.append(Order(
                number=f"SO-{100000 + n}",
                customer=customer,
                created=created,
                placed_time=time(hour, rng.randint(0, 59), rng.randint(0, 59)),
                status=status,
                channel=rng.choices(list(CHANNEL_WEIGHTS), CHANNEL_WEIGHTS.values())[0],
                payment=rng.choices(list(PAYMENT_WEIGHTS), PAYMENT_WEIGHTS.values())[0],
            ))
            lines = rng.choices([1, 2, 3, 4], [50, 30, 14, 6])[0]
            pending_items.append([
                (p, rng.choices([1, 2, 3, 5], [70, 18, 8, 4])[0])
                for p in rng.sample(products, lines)
            ])

        orders = Order.objects.bulk_create(orders)
        items = []
        for order, lines in zip(orders, pending_items):
            for product, qty in lines:
                discount = Decimal("0.9") if qty >= 3 else Decimal("1")
                items.append(OrderItem(
                    order=order, product=product, quantity=qty,
                    unit_price=(product.price * discount).quantize(Decimal("0.01")),
                ))
        OrderItem.objects.bulk_create(items, batch_size=2000)
        return orders

    def _create_events(self, orders, users):
        rng = self.rng
        staff = [users["manager"], users["j.miller"], users["n.tanaka"]]
        flow = ["pending", "paid", "shipped", "delivered"]
        events = []
        now = timezone.now()
        for order in orders:
            at = datetime.combine(order.created, order.placed_time, tzinfo=UTC)
            target = order.status
            steps = flow[: flow.index(target) + 1] if target in flow else flow[: rng.randint(2, 4)]
            for i, status in enumerate(steps):
                if i == 1:
                    at += timedelta(minutes=rng.randint(1, 90))
                elif i == 2:
                    at += timedelta(hours=rng.randint(10, 40))
                elif i == 3:
                    at += timedelta(hours=rng.randint(30, 120))
                if at > now:
                    break
                events.append(OrderEvent(
                    order=order, status=status, created_at=at,
                    user=rng.choice(staff) if status == "shipped" else None,
                    note={
                        "pending": f"Order placed via {order.get_channel_display()}",
                        "paid": f"Payment captured ({order.get_payment_display()})",
                        "shipped": f"Handed to carrier, tracking #1Z{rng.randint(10**8, 10**9 - 1)}",
                        "delivered": "Delivered to customer",
                    }[status],
                ))
            if target == "refunded":
                at = min(at + timedelta(days=rng.randint(2, 12)), now)
                events.append(OrderEvent(
                    order=order, status="refunded", created_at=at, user=rng.choice(staff),
                    note=rng.choice(["Customer changed their mind", "Item arrived damaged",
                                     "Wrong item shipped", "Late delivery"]),
                ))
        OrderEvent.objects.bulk_create(events, batch_size=4000)

    def _create_traffic(self):
        """Back-fill funnel counters from real order counts with plausible conversion rates."""
        rng = self.rng
        per_day = {}
        for created in Order.objects.values_list("created", flat=True):
            per_day[created] = per_day.get(created, 0) + 1
        rows = []
        day = self.start
        while day <= self.today:
            orders = per_day.get(day, 0)
            checkouts = round(orders / rng.uniform(0.66, 0.78)) + rng.randint(0, 2)
            carts = round(checkouts / rng.uniform(0.34, 0.42))
            # Counted in sessions, so every step is a subset of the one before
            views = round(carts / rng.uniform(0.09, 0.13))
            visits = round(views / rng.uniform(0.48, 0.62))
            rows.append(DailyTraffic(date=day, visits=visits, product_views=views,
                                     add_to_cart=carts, checkouts=checkouts))
            day += timedelta(days=1)
        DailyTraffic.objects.bulk_create(rows)

    # ------------------------------------------------------ notifications etc.
    def _create_notifications(self, users, products):
        rng = self.rng
        now = timezone.now()
        templates = []
        big_orders = (
            Order.objects.with_totals().filter(created__gte=self.today - timedelta(days=6))
            .select_related("customer").order_by("-total")[:8]
        )
        for o in big_orders:
            templates.append((Notification.Kind.ORDER, f"New order {o.number}",
                              f"{o.customer.name} placed an order of ${o.total:,.2f}",
                              f"/orders/{o.number}/"))
        for p in [p for p in products if p.stock <= p.reorder_level]:
            title = "Out of stock" if p.stock == 0 else "Low stock"
            templates.append((Notification.Kind.STOCK, f"{title}: {p.name}",
                              f"{p.stock} left, reorder level is {p.reorder_level}",
                              f"/products/{p.pk}/"))
        for o in Order.objects.filter(status="refunded").order_by("-created")[:3]:
            templates.append((Notification.Kind.REFUND, f"Refund issued for {o.number}",
                              "The payment was returned to the customer", f"/orders/{o.number}/"))
        templates.append((Notification.Kind.REPORT, "Weekly sales summary is ready",
                          "Sent to 2 recipients as PDF", "/settings/#reports"))
        templates.append((Notification.Kind.SYSTEM, "Welcome to Pulse Analytics",
                          "Press Ctrl + K anywhere to search orders, customers and products", "/"))

        rows = []
        for user in users.values():
            for k, (kind, title, body, url) in enumerate(templates):
                age = timedelta(minutes=rng.randint(5, 60) + k * rng.randint(40, 300))
                rows.append(Notification(
                    user=user, kind=kind, title=title, body=body, url=url,
                    created_at=now - age, read=k >= 5,
                ))
        Notification.objects.bulk_create(rows)

    def _create_audit_trail(self, users, orders, products):
        rng = self.rng
        now = timezone.now()
        people = list(users.values())
        recent_orders = [o for o in orders if (self.today - o.created).days < 45]
        actions = [
            (AuditLog.Action.LOGIN, 30), (AuditLog.Action.ORDER_STATUS, 25),
            (AuditLog.Action.EXPORT, 14), (AuditLog.Action.STOCK, 12),
            (AuditLog.Action.SETTINGS, 6), (AuditLog.Action.REPORT, 5),
            (AuditLog.Action.ROLE, 2), (AuditLog.Action.LOGOUT, 6),
        ]
        rows = []
        for _ in range(260):
            action = rng.choices([a for a, _ in actions], [w for _, w in actions])[0]
            user = rng.choice(people)
            if action == AuditLog.Action.ORDER_STATUS:
                o = rng.choice(recent_orders)
                target, details = o.number, f"{rng.choice(['Paid', 'Shipped'])} → {o.get_status_display()}"
            elif action == AuditLog.Action.STOCK:
                p = rng.choice(products)
                old = rng.randint(0, 40)
                target, details = p.name, f"Stock {old} → {old + rng.choice([50, 100, 200])}"
            elif action == AuditLog.Action.EXPORT:
                target = rng.choice(["Orders (Excel)", "Orders (CSV)", "Customers (CSV)",
                                     "Products (CSV)", "Sales report (PDF)"])
                details = rng.choice(["Last 30 days", "Last 90 days", "Last 12 months", "All time"])
            elif action == AuditLog.Action.SETTINGS:
                target, details = user.username, rng.choice(
                    ["Currency USD → EUR", "Time zone UTC → Europe/Berlin", "Accent indigo → emerald"])
            elif action == AuditLog.Action.REPORT:
                target, details = "Weekly sales summary", "Sent to 2 recipients"
            elif action == AuditLog.Action.ROLE:
                other = rng.choice(people)
                target, details = other.username, "Viewer → Manager"
            else:
                target, details = user.username, ""
            rows.append(AuditLog(
                user=user, action=action, target=target, details=details,
                ip=f"10.0.{rng.randint(0, 20)}.{rng.randint(2, 250)}",
                created_at=now - timedelta(minutes=rng.randint(30, 60 * 24 * 45)),
            ))
        AuditLog.objects.bulk_create(rows)

    def _create_reports(self, users):
        for username, name, freq, fmt, recipients in [
            ("demo", "Weekly sales summary", "weekly", "pdf", "ceo@example.com, finance@example.com"),
            ("demo", "Daily orders export", "daily", "xlsx", "ops@example.com"),
            ("manager", "Monthly inventory review", "monthly", "csv", "warehouse@example.com"),
        ]:
            ScheduledReport.objects.create(
                user=users[username], name=name, frequency=freq, format=fmt, recipients=recipients,
                last_sent=timezone.now() - timedelta(days=self.rng.randint(1, 6)),
            )
