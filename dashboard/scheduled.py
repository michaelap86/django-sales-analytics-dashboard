"""Build and e-mail scheduled reports."""

import csv
import io
from datetime import date, timedelta
from types import SimpleNamespace

from django.core.mail import EmailMessage
from django.utils import timezone

from . import currency, pdf
from .exports import xlsx_workbook
from .filters import Filters
from .models import Notification, Order, ScheduledReport
from .views.orders import ORDER_HEADERS, _order_rows

PERIOD_DAYS = {"daily": 1, "weekly": 7, "monthly": 30}


def _filters_for(report):
    end = date.today()
    start = end - timedelta(days=PERIOD_DAYS[report.frequency] - 1)
    label = {"daily": "Yesterday & today", "weekly": "Last 7 days", "monthly": "Last 30 days"}[report.frequency]
    return Filters(start=start, end=end, preset="custom"), label


def is_due(report, now=None):
    now = now or timezone.now()
    if not report.active:
        return False
    if report.last_sent is None:
        return True
    gap = {"daily": timedelta(hours=23), "weekly": timedelta(days=6, hours=23),
           "monthly": timedelta(days=27)}[report.frequency]
    return now - report.last_sent >= gap


def send(report):
    filters, label = _filters_for(report)
    currency.activate(report.user.profile.currency)
    if report.format == ScheduledReport.Format.PDF:
        content, mime, ext = pdf.sales_report(filters, report.user), "application/pdf", "pdf"
    else:
        qs = filters.apply_to_orders(Order.objects.with_totals().select_related("customer"))
        if report.format == ScheduledReport.Format.CSV:
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(ORDER_HEADERS)
            w.writerows(_order_rows(qs))
            content, mime, ext = buf.getvalue().encode("utf-8-sig"), "text/csv", "csv"
        else:
            wb = xlsx_workbook("Orders", ORDER_HEADERS, _order_rows(qs),
                               widths=[12, 12, 22, 22, 34, 16, 24, 14, 12, 14], money_col=10, date_col=2)
            buf = io.BytesIO()
            wb.save(buf)
            content, ext = buf.getvalue(), "xlsx"
            mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    recipients = [e.strip() for e in report.recipients.split(",") if e.strip()]
    email = EmailMessage(
        subject=f"[Pulse Analytics] {report.name} - {label}",
        body=(f"Hi,\n\nAttached is your {report.get_frequency_display().lower()} report "
              f"\"{report.name}\" covering {filters.start:%b %d} – {filters.end:%b %d, %Y}.\n\n"
              "- Pulse Analytics (demo)"),
        to=recipients,
    )
    email.attach(f"{report.name.lower().replace(' ', '-')}_{filters.end:%Y%m%d}.{ext}", content, mime)
    email.send()

    report.last_sent = timezone.now()
    report.save(update_fields=["last_sent"])
    Notification.objects.create(
        user=report.user, kind=Notification.Kind.REPORT, title=f"{report.name} sent",
        body=f"Delivered to {len(recipients)} recipient{'s' if len(recipients) != 1 else ''} "
             f"as {report.get_format_display()}",
        url="/settings/#reports", created_at=timezone.now(),
    )
    return SimpleNamespace(recipients=recipients, size=len(content))
