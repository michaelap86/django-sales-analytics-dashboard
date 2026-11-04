from django.contrib import messages
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .. import pdf
from ..activity import audit, notify_all
from ..exports import csv_response, xlsx_response, xlsx_workbook
from ..filters import parse_filters
from ..models import AuditLog, Notification, Order, OrderEvent
from ..roles import MANAGER, role_required
from .common import REGION_NAMES, filter_context

ORDER_SORTS = {
    "date": ("created", "placed_time"), "-date": ("-created", "-placed_time"),
    "total": ("total",), "-total": ("-total",),
    "customer": ("customer__name",), "-customer": ("-customer__name",),
    "number": ("number",), "-number": ("-number",),
}


def filtered_orders(request, filters):
    sort = request.GET.get("sort", "-date")
    if sort not in ORDER_SORTS:
        sort = "-date"
    channel = request.GET.get("channel", "")
    qs = filters.apply_to_orders(Order.objects.with_totals().select_related("customer"))
    if channel in Order.Channel.values:
        qs = qs.filter(channel=channel)
    return qs.order_by(*ORDER_SORTS[sort], "-id"), sort


def orders(request):
    filters = parse_filters(request)
    qs, sort = filtered_orders(request, filters)
    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    return render(request, "dashboard/orders.html", filter_context(
        filters, page="orders", orders_page=page, sort=sort,
    ))


def order_detail(request, number):
    order = get_object_or_404(Order.objects.with_totals().select_related("customer"), number=number)
    items = order.items.select_related("product__category")
    subtotal = order.total or 0
    return render(request, "dashboard/order_detail.html", {
        "page": "orders",
        "order": order,
        "items": items,
        "events": order.events.select_related("user"),
        "region_name": REGION_NAMES[order.customer.region],
        "customer_orders": order.customer.orders.count(),
        "subtotal": subtotal,
    })


@require_POST
@role_required(MANAGER)
def order_status(request, number):
    order = get_object_or_404(Order, number=number)
    new = request.POST.get("status")
    allowed = Order.TRANSITIONS[order.status]
    if new not in allowed:
        messages.error(request, "That status change isn't allowed.")
        return redirect("order_detail", number=number)

    old_label = order.get_status_display()
    order.status = new
    order.save(update_fields=["status"])
    note = request.POST.get("note", "").strip()[:200]
    OrderEvent.objects.create(
        order=order, status=new, created_at=timezone.now(), user=request.user,
        note=note or f"Status changed by {request.user.get_full_name() or request.user.username}",
    )
    audit(request, AuditLog.Action.ORDER_STATUS, order.number, f"{old_label} → {order.get_status_display()}")
    if new == Order.Status.REFUNDED:
        notify_all(Notification.Kind.REFUND, f"Refund issued for {order.number}",
                   note or "The payment was returned to the customer",
                   f"/orders/{order.number}/", exclude=request.user)
    messages.success(request, f"Order {order.number} marked as {order.get_status_display()}.")
    return redirect("order_detail", number=number)


def invoice_pdf(request, number):
    order = get_object_or_404(Order.objects.with_totals().select_related("customer"), number=number)
    response = HttpResponse(pdf.invoice(order), content_type="application/pdf")
    disposition = "attachment" if request.GET.get("download") else "inline"
    response["Content-Disposition"] = f'{disposition}; filename="invoice-{order.number}.pdf"'
    return response


def _order_rows(qs):
    for o in qs.iterator(chunk_size=1000):
        yield [
            o.number, o.created, o.customer.name, o.customer.company, o.customer.email,
            REGION_NAMES[o.customer.region], o.customer.country, o.get_channel_display(),
            o.get_status_display(), float(o.total or 0),
        ]


ORDER_HEADERS = ["Order #", "Date", "Customer", "Company", "Email", "Region", "Country",
                 "Channel", "Status", "Total (USD)"]


def export_orders(request):
    filters = parse_filters(request)
    qs, _ = filtered_orders(request, filters)
    wb = xlsx_workbook("Orders", ORDER_HEADERS, _order_rows(qs),
                       widths=[12, 12, 22, 22, 34, 16, 24, 14, 12, 14], money_col=10, date_col=2)
    audit(request, AuditLog.Action.EXPORT, "Orders (Excel)", filters.label)
    return xlsx_response(f"orders_{filters.start:%Y%m%d}_{filters.end:%Y%m%d}.xlsx", wb)


def export_orders_csv(request):
    filters = parse_filters(request)
    qs, _ = filtered_orders(request, filters)
    audit(request, AuditLog.Action.EXPORT, "Orders (CSV)", filters.label)
    return csv_response(f"orders_{filters.start:%Y%m%d}_{filters.end:%Y%m%d}.csv",
                        ORDER_HEADERS, _order_rows(qs))
