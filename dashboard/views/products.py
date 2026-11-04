from datetime import date, timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, F, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .. import analytics as an
from ..activity import audit, notify_all
from ..currency import as_float
from ..exports import csv_response
from ..models import AuditLog, Category, Notification, Order, OrderItem, Product
from ..roles import MANAGER, role_required

PRODUCT_SORTS = {
    "name": "name", "-name": "-name",
    "price": "price", "-price": "-price",
    "stock": "stock", "-stock": "-stock",
    "sold": "sold_30", "-sold": "-sold_30",
    "revenue": "revenue_30", "-revenue": "-revenue_30",
}


def _with_sales(qs, days=30):
    since = date.today() - timedelta(days=days - 1)
    recent = Q(order_items__order__created__gte=since) & ~Q(order_items__order__status=Order.Status.REFUNDED)
    return qs.annotate(
        sold_30=Sum("order_items__quantity", filter=recent, default=0),
        revenue_30=Sum(F("order_items__quantity") * F("order_items__unit_price"), filter=recent, default=0,
                       output_field=an.MONEY),
    )


def _filtered(request):
    qs = _with_sales(Product.objects.select_related("category"))
    q = request.GET.get("q", "").strip()[:80]
    category = request.GET.get("category", "")
    stock = request.GET.get("stock", "")
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(sku__icontains=q))
    if category.isdigit():
        qs = qs.filter(category_id=category)
    if stock == "low":
        qs = qs.filter(stock__gt=0, stock__lte=F("reorder_level"))
    elif stock == "out":
        qs = qs.filter(stock=0)
    elif stock == "ok":
        qs = qs.filter(stock__gt=F("reorder_level"))
    sort = request.GET.get("sort", "-revenue")
    if sort not in PRODUCT_SORTS:
        sort = "-revenue"
    return qs.order_by(PRODUCT_SORTS[sort], "id"), {"q": q, "category": category, "stock": stock, "sort": sort}


def products(request):
    qs, params = _filtered(request)
    page = Paginator(qs, 25).get_page(request.GET.get("page"))
    all_products = Product.objects.all()
    inventory_value = sum(p.stock * p.cost for p in all_products)
    summary = {
        "count": all_products.count(),
        "low": all_products.filter(stock__gt=0, stock__lte=F("reorder_level")).count(),
        "out": all_products.filter(stock=0).count(),
        "inventory_value": inventory_value,
        "units": sum(p.stock for p in all_products),
    }
    base = {k: v for k, v in params.items() if v and k != "sort"}
    return render(request, "dashboard/products.html", {
        "page": "products",
        "products_page": page,
        "params": params,
        "base_params": base,
        "categories": Category.objects.annotate(n=Count("products")),
        "summary": summary,
    })


def product_detail(request, pk):
    product = get_object_or_404(_with_sales(Product.objects.select_related("category")), pk=pk)
    items = OrderItem.objects.filter(product=product).exclude(order__status=Order.Status.REFUNDED)
    today = date.today()
    start = today - timedelta(days=179)
    labels, revenue, units_series = an.series(items, start, today, 7)
    # Average weekly sales over the last 12 weeks, used for the stock run-out estimate
    sold_12w = items.filter(order__created__gte=today - timedelta(days=83)).aggregate(u=Sum("quantity"))["u"]
    weekly_units = (sold_12w or 0) / 12
    lifetime = items.aggregate(units=Sum("quantity"), revenue=Sum(an.REVENUE), orders=Count("order", distinct=True))
    days_left = round(product.stock / (weekly_units / 7)) if weekly_units else None

    top_buyers = (
        items.values("order__customer__id", "order__customer__name", "order__customer__company")
        .annotate(units=Sum("quantity")).order_by("-units")[:5]
    )
    recent = (
        items.select_related("order__customer").order_by("-order__created", "-order__placed_time")[:10]
    )
    return render(request, "dashboard/product_detail.html", {
        "page": "products",
        "product": product,
        "lifetime": lifetime,
        "weekly_units": weekly_units,
        "days_left": days_left,
        "top_buyers": top_buyers,
        "recent_items": recent,
        "chart_data": {
            "labels": labels,
            "revenue": [as_float(v) for v in revenue],
            "units": units_series,
        },
    })


@require_POST
@role_required(MANAGER)
def product_stock(request, pk):
    product = get_object_or_404(Product, pk=pk)
    try:
        amount = int(request.POST.get("amount", ""))
    except ValueError:
        messages.error(request, "Enter a whole number.")
        return redirect("product_detail", pk=pk)
    mode = request.POST.get("mode", "add")
    old = product.stock
    new = old + amount if mode == "add" else amount
    if new < 0 or new > 100000:
        messages.error(request, "Stock must be between 0 and 100,000.")
        return redirect("product_detail", pk=pk)

    product.stock = new
    reorder = request.POST.get("reorder_level", "")
    if reorder.isdigit():
        product.reorder_level = int(reorder)
    product.save(update_fields=["stock", "reorder_level"])
    audit(request, AuditLog.Action.STOCK, product.name, f"Stock {old} → {new}")
    if new <= product.reorder_level:
        title = "Out of stock" if new == 0 else "Low stock"
        notify_all(Notification.Kind.STOCK, f"{title}: {product.name}",
                   f"{new} left, reorder level is {product.reorder_level}",
                   f"/products/{product.pk}/", exclude=request.user)
    messages.success(request, f"Stock for {product.name} updated: {old} → {new}.")
    return redirect("product_detail", pk=pk)


def export_products_csv(request):
    qs, _ = _filtered(request)
    rows = (
        [p.sku, p.name, p.category.name, float(p.price), float(p.cost), round(p.margin, 1),
         p.stock, p.reorder_level, p.stock_status, p.sold_30, float(p.revenue_30)]
        for p in qs
    )
    audit(request, AuditLog.Action.EXPORT, "Products (CSV)")
    return csv_response("products.csv", [
        "SKU", "Name", "Category", "Price (USD)", "Cost (USD)", "Margin %", "Stock",
        "Reorder level", "Stock status", "Units sold (30d)", "Revenue 30d (USD)",
    ], rows)
