from datetime import date

from django.db.models import Count, Sum
from django.http import HttpResponse
from django.shortcuts import render

from .. import analytics as an
from .. import pdf
from ..activity import audit
from ..currency import as_float
from ..filters import parse_filters
from ..models import AuditLog, Customer, Order, OrderItem
from .common import REGION_NAMES, filter_context

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def reports(request):
    filters = parse_filters(request)
    today = date.today()
    items = filters.apply_to_items(OrderItem.objects.all())
    dimension_items = filters.apply_dimensions(OrderItem.objects.all())
    orders = filters.apply_to_orders(Order.objects.all())
    order_count = orders.count()

    yoy = an.year_over_year(dimension_items, today)
    fc = an.forecast(dimension_items, today)
    cohort_rows = an.cohorts(Order.objects.exclude(status=Order.Status.REFUNDED), today)
    heat = an.heatmap(orders)
    funnel = an.funnel(filters.start, filters.end, order_count)

    channels = list(
        items.values("order__channel").annotate(revenue=Sum(an.REVENUE), orders=Count("order", distinct=True))
        .order_by("-revenue")
    )
    channel_labels = dict(Order.Channel.choices)
    channel_total = sum(c["revenue"] for c in channels) or 1
    for c in channels:
        c["label"] = channel_labels[c["order__channel"]]
        c["share"] = float(c["revenue"] / channel_total * 100)
        c["aov"] = c["revenue"] / c["orders"] if c["orders"] else 0

    payments = dict(orders.values("payment").annotate(n=Count("id")).values_list("payment", "n"))

    chart_data = {
        "yoy": {
            "labels": yoy["labels"],
            "thisYear": [as_float(v) if v is not None else None for v in yoy["this_year"]],
            "lastYear": [as_float(v) for v in yoy["last_year"]],
            "year": yoy["year"],
        },
        "forecast": fc and {
            "labels": fc["labels"],
            "actual": [as_float(v) if v is not None else None for v in fc["actual"]],
            "predicted": [as_float(v) if v is not None else None for v in fc["predicted"]],
            "low": [as_float(v) if v is not None else None for v in fc["low"]],
            "high": [as_float(v) if v is not None else None for v in fc["high"]],
        },
        "channels": {
            "labels": [c["label"] for c in channels],
            "values": [as_float(c["revenue"]) for c in channels],
        },
        "payments": {
            "labels": [label for _, label in Order.Payment.choices],
            "values": [payments.get(v, 0) for v, _ in Order.Payment.choices],
        },
    }

    repeat = Customer.objects.annotate(n=Count("orders")).filter(n__gte=2).count()
    buyers = Customer.objects.annotate(n=Count("orders")).filter(n__gte=1).count()

    return render(request, "dashboard/reports.html", filter_context(
        filters,
        page="reports",
        yoy=yoy,
        forecast=fc,
        cohorts=cohort_rows,
        cohort_offsets=range(len(cohort_rows[0]["cells"]) if cohort_rows else 0),
        heat=heat,
        heat_rows=list(zip(WEEKDAYS, heat["grid"])),
        hours=range(24),
        funnel=funnel,
        conversion=funnel[-1]["value"] / funnel[0]["value"] * 100 if funnel[0]["value"] else 0,
        channels=channels,
        repeat_rate=repeat / buyers * 100 if buyers else 0,
        chart_data=chart_data,
    ))


def geography(request):
    filters = parse_filters(request)
    items = filters.apply_to_items(OrderItem.objects.all())
    prev_start, prev_end = filters.previous
    prev = dict(
        filters.apply_to_items(OrderItem.objects.all(), prev_start, prev_end)
        .values("order__customer__country").annotate(revenue=Sum(an.REVENUE))
        .values_list("order__customer__country", "revenue")
    )
    rows = list(
        items.values("order__customer__country", "order__customer__region")
        .annotate(revenue=Sum(an.REVENUE), orders=Count("order", distinct=True),
                  customers=Count("order__customer", distinct=True))
        .order_by("-revenue")
    )
    total = sum(r["revenue"] for r in rows) or 1
    for r in rows:
        r["share"] = float(r["revenue"] / total * 100)
        r["region_name"] = REGION_NAMES[r["order__customer__region"]]
        r["change"] = an.pct_change(r["revenue"], prev.get(r["order__customer__country"]))
        r["aov"] = r["revenue"] / r["orders"] if r["orders"] else 0

    regions = {}
    for r in rows:
        reg = regions.setdefault(r["order__customer__region"], {
            "name": r["region_name"], "revenue": 0, "orders": 0, "countries": 0})
        reg["revenue"] += r["revenue"]
        reg["orders"] += r["orders"]
        reg["countries"] += 1
    region_list = sorted(regions.values(), key=lambda x: -x["revenue"])
    for reg in region_list:
        reg["share"] = float(reg["revenue"] / total * 100)

    return render(request, "dashboard/geography.html", filter_context(
        filters,
        page="geography",
        countries=rows,
        region_list=region_list,
        chart_data={
            "countries": {r["order__customer__country"]: as_float(r["revenue"]) for r in rows},
        },
    ))


def report_pdf(request):
    filters = parse_filters(request)
    response = HttpResponse(pdf.sales_report(filters, request.user), content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="sales-report_{filters.start:%Y%m%d}_{filters.end:%Y%m%d}.pdf"'
    )
    audit(request, AuditLog.Action.EXPORT, "Sales report (PDF)", filters.label)
    return response
