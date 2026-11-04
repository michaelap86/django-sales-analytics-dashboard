from collections import Counter
from datetime import date, timedelta
from decimal import Decimal

from django.core.paginator import Paginator
from django.db.models import Case, CharField, Count, F, Q, Sum, Value, When
from django.shortcuts import get_object_or_404, render

from .. import analytics as an
from ..activity import audit
from ..currency import as_float
from ..exports import csv_response
from ..models import AuditLog, Customer, Order, OrderItem, Region
from .common import REGION_NAMES

SEGMENTS = [
    ("vip", "VIP", "Top 10% by lifetime spend"),
    ("new", "New", "Joined in the last 45 days"),
    ("loyal", "Loyal", "4+ orders and active"),
    ("active", "Active", "Ordered in the last 90 days"),
    ("at_risk", "At risk", "No order for 90–180 days"),
    ("inactive", "Inactive", "No order for 180+ days"),
]
SEGMENT_LABELS = {k: v for k, v, _ in SEGMENTS}

CUSTOMER_SORTS = {
    "name": "name", "-name": "-name",
    "spent": "spent", "-spent": "-spent",
    "orders": "order_count", "-orders": "-order_count",
    "last": "last_order", "-last": "-last_order",
    "joined": "joined", "-joined": "-joined",
}


def vip_threshold():
    """Lifetime spend at the 90th percentile."""
    spends = sorted(
        s for s in Customer.objects.annotate(**an.customer_stats()).values_list("spent", flat=True) if s
    )
    return spends[int(len(spends) * 0.9)] if spends else Decimal(0)


def with_segments(qs, today=None):
    today = today or date.today()
    qs = qs.annotate(**an.customer_stats())
    return qs.annotate(segment=Case(
        When(spent__gte=vip_threshold(), then=Value("vip")),
        When(joined__gte=today - timedelta(days=45), then=Value("new")),
        When(Q(last_order__isnull=True) | Q(last_order__lt=today - timedelta(days=180)), then=Value("inactive")),
        When(last_order__lt=today - timedelta(days=90), then=Value("at_risk")),
        When(order_count__gte=4, then=Value("loyal")),
        default=Value("active"),
        output_field=CharField(),
    ))


def _filtered(request):
    qs = with_segments(Customer.objects.all())
    q = request.GET.get("q", "").strip()[:80]
    region = request.GET.get("region", "")
    segment = request.GET.get("segment", "")
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(email__icontains=q) | Q(company__icontains=q)
                       | Q(country__icontains=q))
    if region in Region.values:
        qs = qs.filter(region=region)
    if segment in SEGMENT_LABELS:
        qs = qs.filter(segment=segment)
    sort = request.GET.get("sort", "-spent")
    if sort not in CUSTOMER_SORTS:
        sort = "-spent"
    field = CUSTOMER_SORTS[sort]
    # Customers without orders have no spend/last order; keep them at the bottom either way
    if field.startswith("-"):
        order_expr = F(field[1:]).desc(nulls_last=True)
    else:
        order_expr = F(field).asc(nulls_last=True)
    return qs.order_by(order_expr, "id"), {"q": q, "region": region, "segment": segment, "sort": sort}


def customers(request):
    qs, params = _filtered(request)
    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    # The segment is built from aggregates, so SQL can't GROUP BY it; count in Python
    counts = Counter(with_segments(Customer.objects.all()).order_by().values_list("segment", flat=True))
    segments = [
        {"key": k, "label": label, "hint": hint, "count": counts.get(k, 0)}
        for k, label, hint in SEGMENTS
    ]
    base = {k: v for k, v in params.items() if v and k != "sort"}
    return render(request, "dashboard/customers.html", {
        "page": "customers",
        "customers_page": page,
        "params": params,
        "base_params": base,
        "segments": segments,
        "segment_labels": SEGMENT_LABELS,
        "regions": Region.choices,
        "region_names": REGION_NAMES,
        "total_customers": sum(counts.values()),
    })


def customer_detail(request, pk):
    customer = get_object_or_404(with_segments(Customer.objects.all()), pk=pk)
    orders = customer.orders.with_totals().order_by("-created", "-placed_time")
    items = OrderItem.objects.filter(order__customer=customer).exclude(order__status=Order.Status.REFUNDED)

    monthly = an.monthly_revenue(items)
    months = sorted(monthly)
    if months:
        first, last = months[0], date.today().replace(day=1)
        labels, values, m = [], [], first
        while m <= last:
            labels.append(m.isoformat())
            values.append(as_float(monthly.get(m, 0)))
            m = (m.replace(day=28) + timedelta(days=4)).replace(day=1)
    else:
        labels, values = [], []

    by_category = list(
        items.values("product__category__name", "product__category__color")
        .annotate(revenue=Sum(an.REVENUE)).order_by("-revenue")
    )
    favourites = (
        items.values("product__id", "product__name").annotate(units=Sum("quantity"), revenue=Sum(an.REVENUE))
        .order_by("-units")[:5]
    )
    order_count = customer.order_count or 0
    stats = {
        "spent": customer.spent or 0,
        "orders": order_count,
        "aov": (customer.spent or 0) / order_count if order_count else 0,
        "refunds": orders.filter(status=Order.Status.REFUNDED).count(),
        "days_since": (date.today() - customer.last_order).days if customer.last_order else None,
    }
    return render(request, "dashboard/customer_detail.html", {
        "page": "customers",
        "customer": customer,
        "segment_label": SEGMENT_LABELS[customer.segment],
        "region_name": REGION_NAMES[customer.region],
        "orders": orders[:25],
        "stats": stats,
        "by_category": by_category,
        "favourites": favourites,
        "chart_data": {
            "labels": labels, "values": values,
            "categories": {
                "labels": [c["product__category__name"] for c in by_category],
                "values": [as_float(c["revenue"]) for c in by_category],
                "colors": [c["product__category__color"] for c in by_category],
            },
        },
    })


def export_customers_csv(request):
    qs, _ = _filtered(request)
    rows = (
        [c.name, c.email, c.phone, c.company, REGION_NAMES[c.region], c.country, c.joined,
         SEGMENT_LABELS[c.segment], c.order_count, float(c.spent or 0), c.last_order or ""]
        for c in qs
    )
    audit(request, AuditLog.Action.EXPORT, "Customers (CSV)")
    return csv_response("customers.csv", [
        "Name", "Email", "Phone", "Company", "Region", "Country", "Joined", "Segment",
        "Orders", "Lifetime spend (USD)", "Last order",
    ], rows)
