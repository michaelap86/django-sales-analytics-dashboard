from django.db.models import Count, F, Sum
from django.shortcuts import render

from .. import analytics as an
from ..currency import as_float
from ..filters import parse_filters
from ..models import Customer, Order, OrderItem, Product
from .common import REGION_NAMES, filter_context


def dashboard(request):
    filters = parse_filters(request)
    base = OrderItem.objects.all()
    items = filters.apply_to_items(base)
    prev_start, prev_end = filters.previous
    prev_items = filters.apply_to_items(base, prev_start, prev_end)

    current, previous = an.totals(items), an.totals(prev_items)
    customers = Customer.objects.filter(region=filters.region) if filters.region else Customer.objects
    new_customers = customers.filter(joined__range=(filters.start, filters.end)).count()
    prev_new_customers = customers.filter(joined__range=(prev_start, prev_end)).count()

    kpis = [
        {"label": "Revenue", "value": current["revenue"], "fmt": "money",
         "change": an.pct_change(current["revenue"], previous["revenue"]), "icon": "revenue"},
        {"label": "Orders", "value": current["orders"], "fmt": "int",
         "change": an.pct_change(current["orders"], previous["orders"]), "icon": "orders"},
        {"label": "Avg. order value", "value": current["aov"], "fmt": "money",
         "change": an.pct_change(current["aov"], previous["aov"]), "icon": "aov"},
        {"label": "Gross profit", "value": current["profit"], "fmt": "money",
         "change": an.pct_change(current["profit"], previous["profit"]), "icon": "profit",
         "note": f"{current['margin']:.1f}% margin"},
        {"label": "New customers", "value": new_customers, "fmt": "int",
         "change": an.pct_change(new_customers, prev_new_customers), "icon": "customers"},
    ]

    size, unit = an.bucket_size(filters.days)
    labels, revenue, orders = an.series(items, filters.start, filters.end, size)
    _, prev_revenue, _ = an.series(prev_items, prev_start, prev_end, size)

    by_category = list(
        items.values("product__category__name", "product__category__color")
        .annotate(revenue=Sum(an.REVENUE)).order_by("-revenue")
    )
    by_region = list(
        items.values("order__customer__region").annotate(revenue=Sum(an.REVENUE)).order_by("-revenue")
    )
    status_counts = dict(
        filters.apply_to_orders(Order.objects.all()).order_by()
        .values("status").annotate(n=Count("id")).values_list("status", "n")
    )

    top_products = (
        items.values("product__id", "product__name", "product__category__name", "product__category__color")
        .annotate(revenue=Sum(an.REVENUE), units=Sum("quantity"))
        .order_by("-revenue")[:6]
    )
    top_customers = list(
        items.values("order__customer__id", "order__customer__name", "order__customer__company",
                     "order__customer__region")
        .annotate(revenue=Sum(an.REVENUE), orders=Count("order", distinct=True))
        .order_by("-revenue")[:6]
    )
    for c in top_customers:
        c["region_name"] = REGION_NAMES[c["order__customer__region"]]

    recent_orders = filters.apply_to_orders(
        Order.objects.with_totals().select_related("customer"))[:8]
    low_stock = Product.objects.filter(stock__lte=F("reorder_level")).order_by("stock")[:5]

    chart_data = {
        "unit": unit,
        "labels": labels,
        "revenue": [as_float(v) for v in revenue],
        "previousRevenue": [as_float(v) for v in prev_revenue],
        "orders": orders,
        "categories": {
            "labels": [c["product__category__name"] for c in by_category],
            "values": [as_float(c["revenue"]) for c in by_category],
            "colors": [c["product__category__color"] for c in by_category],
        },
        "regions": {
            "labels": [REGION_NAMES[r["order__customer__region"]] for r in by_region],
            "values": [as_float(r["revenue"]) for r in by_region],
        },
        "statuses": {
            "labels": [label for _, label in Order.Status.choices],
            "values": [status_counts.get(value, 0) for value, _ in Order.Status.choices],
        },
    }

    return render(request, "dashboard/dashboard.html", filter_context(
        filters,
        page="dashboard",
        kpis=kpis,
        chart_data=chart_data,
        by_category=by_category,
        top_products=top_products,
        top_customers=top_customers,
        recent_orders=recent_orders,
        low_stock=low_stock,
        category_total=sum(c["revenue"] for c in by_category) or 1,
    ))
