"""Aggregations shared by the overview, reports and PDF export."""

import statistics
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Max, Q, Sum

from .models import DailyTraffic, Order

MONEY = DecimalField(max_digits=14, decimal_places=2)
REVENUE = ExpressionWrapper(F("quantity") * F("unit_price"), output_field=MONEY)
COST = ExpressionWrapper(F("quantity") * F("product__cost"), output_field=MONEY)


def pct_change(current, previous):
    if not previous:
        return None
    return float((current - previous) / previous * 100)


def totals(items):
    agg = items.aggregate(
        revenue=Sum(REVENUE), cost=Sum(COST),
        orders=Count("order", distinct=True), units=Sum("quantity"),
    )
    revenue = agg["revenue"] or Decimal(0)
    profit = revenue - (agg["cost"] or Decimal(0))
    orders = agg["orders"] or 0
    return {
        "revenue": revenue,
        "profit": profit,
        "margin": float(profit / revenue * 100) if revenue else 0.0,
        "orders": orders,
        "units": agg["units"] or 0,
        "aov": revenue / orders if orders else Decimal(0),
    }


def bucket_size(days):
    """Pick a chart resolution (bucket size in days) that keeps the series readable."""
    if days <= 45:
        return 1, "day"
    if days <= 200:
        return 7, "week"
    return 30, "month"


def series(items, start, end, size):
    """Revenue/orders in fixed-size buckets counted back from `end`.

    Buckets are aligned to the period end, and leftover days at the start are
    dropped, so there are no partial buckets that would dip the line.
    """
    daily = {
        r["order__created"]: r
        for r in items.values("order__created")
        .annotate(revenue=Sum(REVENUE), orders=Count("order", distinct=True))
    }
    count = ((end - start).days + 1) // size
    first = end - timedelta(days=count * size - 1)
    labels, revenue, orders = [], [], []
    for b in range(count):
        bucket_start = first + timedelta(days=b * size)
        days = [daily.get(bucket_start + timedelta(days=i), {}) for i in range(size)]
        labels.append(bucket_start.isoformat())
        revenue.append(sum((d.get("revenue") or 0 for d in days), Decimal(0)))
        orders.append(sum(d.get("orders") or 0 for d in days))
    return labels, revenue, orders


def _month_start(d):
    return d.replace(day=1)


def _add_months(d, n):
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, 1)


def monthly_revenue(items):
    """{first-of-month: revenue} for every month that has sales."""
    out = defaultdict(Decimal)
    for row in items.values("order__created").annotate(revenue=Sum(REVENUE)):
        out[_month_start(row["order__created"])] += row["revenue"] or 0
    return dict(out)


def year_over_year(items, today):
    """This year's monthly revenue next to the same months last year."""
    by_month = monthly_revenue(items)
    labels, this_year, last_year = [], [], []
    for m in range(1, 13):
        cur, prev = date(today.year, m, 1), date(today.year - 1, m, 1)
        labels.append(cur.strftime("%b"))
        this_year.append(by_month.get(cur) if cur <= today else None)
        last_year.append(by_month.get(prev, Decimal(0)))
    ytd = sum((v for v in this_year if v is not None), Decimal(0))
    prev_ytd = sum((last_year[m - 1] for m in range(1, today.month + 1)), Decimal(0))
    # Current month is partial, so compare it with the same share of last year's month
    days_in_month = (_add_months(date(today.year, today.month, 1), 1) - timedelta(days=1)).day
    prev_ytd -= last_year[today.month - 1] * (1 - Decimal(today.day) / days_in_month)
    return {
        "labels": labels, "this_year": this_year, "last_year": last_year,
        "year": today.year, "ytd": ytd, "prev_ytd": prev_ytd, "change": pct_change(ytd, prev_ytd),
    }


def forecast(items, today, horizon=6, history=18):
    """Linear trend × month-of-year seasonality, fitted on complete months.

    Returns history and forecast series with an approximate 80% band.
    """
    by_month = monthly_revenue(items)
    last_full = _add_months(_month_start(today), -1)
    months = [m for m in sorted(by_month) if m <= last_full]
    if len(months) < 6:
        return None
    ys = [float(by_month[m]) for m in months]
    xs = list(range(len(ys)))
    x_mean, y_mean = statistics.fmean(xs), statistics.fmean(ys)
    slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / sum((x - x_mean) ** 2 for x in xs)
    intercept = y_mean - slope * x_mean

    ratios = defaultdict(list)
    for x, y, m in zip(xs, ys, months):
        trend = intercept + slope * x
        if trend > 0:
            ratios[m.month].append(y / trend)
    season = {k: statistics.fmean(v) for k, v in ratios.items()}
    residuals = [
        y / (intercept + slope * x) / season.get(m.month, 1) - 1
        for x, y, m in zip(xs, ys, months) if intercept + slope * x > 0
    ]
    spread = statistics.pstdev(residuals) * 1.28 if len(residuals) > 2 else 0.1

    shown = months[-history:]
    labels = [m.isoformat() for m in shown]
    actual = [ys[months.index(m)] for m in shown]
    predicted, low, high = [None] * len(shown), [None] * len(shown), [None] * len(shown)
    # Connect the forecast line to the last actual point
    predicted[-1] = low[-1] = high[-1] = actual[-1]
    for h in range(1, horizon + 1):
        m = _add_months(last_full, h)
        value = max(0.0, (intercept + slope * (len(ys) - 1 + h)) * season.get(m.month, 1))
        labels.append(m.isoformat())
        actual.append(None)
        predicted.append(value)
        low.append(value * (1 - spread))
        high.append(value * (1 + spread))
    next_total = sum(v for v in predicted[len(shown):])
    last_total = sum(ys[-horizon:])
    return {
        "labels": labels, "actual": actual, "predicted": predicted, "low": low, "high": high,
        "next_total": next_total, "change": pct_change(next_total, last_total) if last_total else None,
        "monthly_growth": slope, "spread": spread * 100,
    }


def cohorts(orders, today, count=12):
    """Monthly retention: share of each first-purchase cohort that ordered again N months later."""
    first_month, active = {}, defaultdict(set)
    for customer_id, created in orders.order_by("created").values_list("customer_id", "created"):
        m = _month_start(created)
        first_month.setdefault(customer_id, m)
        active[customer_id].add(m)
    newest = _month_start(today)
    rows = []
    for i in range(count - 1, -1, -1):
        cohort = _add_months(newest, -i)
        members = [c for c, m in first_month.items() if m == cohort]
        cells = []
        for offset in range(count):
            month = _add_months(cohort, offset)
            if month > newest:
                cells.append(None)
                continue
            if offset == 0:
                cells.append(100.0 if members else None)
                continue
            returned = sum(1 for c in members if month in active[c])
            cells.append(returned / len(members) * 100 if members else None)
        rows.append({"month": cohort, "size": len(members), "cells": cells})
    return rows


def heatmap(orders):
    """Order counts by weekday (Mon=0) × hour."""
    grid = [[0] * 24 for _ in range(7)]
    for created, placed in orders.values_list("created", "placed_time"):
        grid[created.weekday()][placed.hour] += 1
    peak = max(max(row) for row in grid) or 1
    return {"grid": grid, "peak": peak}


def funnel(start, end, orders_count):
    agg = DailyTraffic.objects.filter(date__range=(start, end)).aggregate(
        visits=Sum("visits"), views=Sum("product_views"), carts=Sum("add_to_cart"),
        checkouts=Sum("checkouts"),
    )
    steps = [
        ("Store visits", agg["visits"] or 0),
        ("Viewed a product", agg["views"] or 0),
        ("Added to cart", agg["carts"] or 0),
        ("Checkout started", agg["checkouts"] or 0),
        ("Orders placed", orders_count),
    ]
    top = steps[0][1] or 1
    out = []
    for i, (label, value) in enumerate(steps):
        prev = steps[i - 1][1] if i else value
        out.append({
            "label": label, "value": value, "pct": value / top * 100,
            "step": value / prev * 100 if prev else 0,
        })
    return out


def customer_stats():
    """Annotations used for customer lists and segments."""
    return {
        "spent": Sum(
            F("orders__items__quantity") * F("orders__items__unit_price"),
            output_field=MONEY, filter=~Q(orders__status=Order.Status.REFUNDED),
        ),
        "order_count": Count("orders", distinct=True),
        "last_order": Max("orders__created"),
    }
