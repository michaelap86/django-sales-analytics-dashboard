from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import DecimalField, ExpressionWrapper, F, Sum


class Category(models.Model):
    name = models.CharField(max_length=60, unique=True)
    color = models.CharField(max_length=7, default="#6366f1")

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField(max_length=120)
    sku = models.CharField(max_length=20, unique=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    price = models.DecimalField(max_digits=10, decimal_places=2)
    cost = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.PositiveIntegerField(default=0)
    reorder_level = models.PositiveIntegerField(default=20)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def margin(self):
        return float((self.price - self.cost) / self.price * 100) if self.price else 0.0

    @property
    def stock_status(self):
        if self.stock == 0:
            return "out"
        if self.stock <= self.reorder_level:
            return "low"
        return "ok"


class Region(models.TextChoices):
    NORTH_AMERICA = "NA", "North America"
    EUROPE = "EU", "Europe"
    ASIA = "AS", "Asia Pacific"
    MIDDLE_EAST = "ME", "Middle East"
    LATIN_AMERICA = "LA", "Latin America"


# Country names match the `world-atlas` map so the choropleth can join on them
COUNTRIES = {
    Region.NORTH_AMERICA: ["United States of America", "Canada", "Mexico"],
    Region.EUROPE: ["United Kingdom", "Germany", "France", "Netherlands", "Spain", "Italy", "Sweden", "Poland"],
    Region.ASIA: ["Japan", "South Korea", "Australia", "India", "China"],
    Region.MIDDLE_EAST: ["United Arab Emirates", "Saudi Arabia", "Turkey", "Qatar"],
    Region.LATIN_AMERICA: ["Brazil", "Argentina", "Chile", "Colombia"],
}


class Customer(models.Model):
    name = models.CharField(max_length=120)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=30, blank=True)
    company = models.CharField(max_length=120, blank=True)
    region = models.CharField(max_length=2, choices=Region.choices)
    country = models.CharField(max_length=60)
    joined = models.DateField()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class OrderQuerySet(models.QuerySet):
    def with_totals(self):
        line_total = ExpressionWrapper(
            F("items__quantity") * F("items__unit_price"),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
        return self.annotate(total=Sum(line_total))


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        SHIPPED = "shipped", "Shipped"
        DELIVERED = "delivered", "Delivered"
        REFUNDED = "refunded", "Refunded"

    class Channel(models.TextChoices):
        WEB = "web", "Web store"
        MOBILE = "mobile", "Mobile app"
        MARKETPLACE = "marketplace", "Marketplace"
        SALES = "sales", "Direct sales"

    class Payment(models.TextChoices):
        CARD = "card", "Credit card"
        PAYPAL = "paypal", "PayPal"
        BANK = "bank", "Bank transfer"

    # Allowed manual status changes
    TRANSITIONS = {
        Status.PENDING: [Status.PAID, Status.REFUNDED],
        Status.PAID: [Status.SHIPPED, Status.REFUNDED],
        Status.SHIPPED: [Status.DELIVERED, Status.REFUNDED],
        Status.DELIVERED: [Status.REFUNDED],
        Status.REFUNDED: [],
    }

    number = models.CharField(max_length=12, unique=True)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="orders")
    created = models.DateField(db_index=True)
    placed_time = models.TimeField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    channel = models.CharField(max_length=12, choices=Channel.choices, default=Channel.WEB)
    payment = models.CharField(max_length=10, choices=Payment.choices, default=Payment.CARD)

    objects = OrderQuerySet.as_manager()

    class Meta:
        ordering = ["-created", "-placed_time", "-id"]

    def __str__(self):
        return self.number

    @property
    def next_statuses(self):
        return [(s, Order.Status(s).label) for s in self.TRANSITIONS[self.status]]


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="order_items")
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    @property
    def line_total(self) -> Decimal:
        return self.quantity * self.unit_price


class OrderEvent(models.Model):
    """One step on an order's timeline."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="events")
    status = models.CharField(max_length=10, choices=Order.Status.choices)
    created_at = models.DateTimeField()
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["created_at", "id"]


class DailyTraffic(models.Model):
    """Store-front funnel counters, one row per day."""

    date = models.DateField(unique=True)
    visits = models.PositiveIntegerField()
    product_views = models.PositiveIntegerField()
    add_to_cart = models.PositiveIntegerField()
    checkouts = models.PositiveIntegerField()

    class Meta:
        ordering = ["date"]


class Profile(models.Model):
    CURRENCIES = [("USD", "US Dollar ($)"), ("EUR", "Euro (€)"), ("GBP", "British Pound (£)")]
    ACCENTS = [
        ("indigo", "Indigo"), ("blue", "Ocean"), ("emerald", "Emerald"),
        ("violet", "Violet"), ("rose", "Rose"), ("amber", "Amber"),
    ]
    TIMEZONES = [
        "UTC", "Europe/London", "Europe/Berlin", "Europe/Istanbul", "Asia/Dubai", "Asia/Tehran",
        "Asia/Kolkata", "Asia/Tokyo", "Australia/Sydney", "America/New_York", "America/Chicago",
        "America/Los_Angeles", "America/Sao_Paulo",
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    job_title = models.CharField(max_length=80, blank=True)
    currency = models.CharField(max_length=3, choices=CURRENCIES, default="USD")
    timezone = models.CharField(max_length=40, default="UTC")
    accent = models.CharField(max_length=10, choices=ACCENTS, default="indigo")
    # Shared demo accounts can't change their password or be deactivated
    is_demo = models.BooleanField(default=False)

    def __str__(self):
        return f"Profile of {self.user}"


class AuditLog(models.Model):
    class Action(models.TextChoices):
        LOGIN = "login", "Signed in"
        LOGOUT = "logout", "Signed out"
        ORDER_STATUS = "order_status", "Changed order status"
        STOCK = "stock", "Updated stock"
        EXPORT = "export", "Exported data"
        ROLE = "role", "Changed user role"
        USER_ACTIVE = "user_active", "Changed user access"
        SETTINGS = "settings", "Updated settings"
        PASSWORD = "password", "Changed password"
        REPORT = "report", "Scheduled report"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=20, choices=Action.choices)
    target = models.CharField(max_length=120, blank=True)
    details = models.CharField(max_length=255, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class Notification(models.Model):
    class Kind(models.TextChoices):
        ORDER = "order", "Order"
        STOCK = "stock", "Inventory"
        REFUND = "refund", "Refund"
        REPORT = "report", "Report"
        SYSTEM = "system", "System"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    title = models.CharField(max_length=120)
    body = models.CharField(max_length=255, blank=True)
    url = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(db_index=True)
    read = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at", "-id"]


class ScheduledReport(models.Model):
    class Frequency(models.TextChoices):
        DAILY = "daily", "Daily"
        WEEKLY = "weekly", "Weekly (Mondays)"
        MONTHLY = "monthly", "Monthly (1st)"

    class Format(models.TextChoices):
        PDF = "pdf", "PDF summary"
        CSV = "csv", "CSV orders"
        XLSX = "xlsx", "Excel orders"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reports")
    name = models.CharField(max_length=80)
    frequency = models.CharField(max_length=10, choices=Frequency.choices, default=Frequency.WEEKLY)
    format = models.CharField(max_length=5, choices=Format.choices, default=Format.PDF)
    recipients = models.CharField(max_length=255, help_text="Comma-separated e-mail addresses")
    active = models.BooleanField(default=True)
    last_sent = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
