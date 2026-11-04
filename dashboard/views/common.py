from django.urls import reverse

from ..filters import PRESETS
from ..models import Category, Order, Region

REGION_NAMES = dict(Region.choices)


def sales_exports(filters):
    qs = filters.querystring()
    return [
        ("Sales report (PDF)", f"{reverse('report_pdf')}?{qs}", "KPIs, charts and top products"),
        ("Orders (Excel)", f"{reverse('export_orders')}?{qs}", "Filtered orders with totals"),
        ("Orders (CSV)", f"{reverse('export_orders_csv')}?{qs}", "Plain text, any spreadsheet tool"),
    ]


def filter_context(filters, **extra):
    return {
        "filters": filters,
        "exports": sales_exports(filters),
        "presets": PRESETS,
        "categories": Category.objects.all(),
        "regions": Region.choices,
        "statuses": Order.Status.choices,
        **extra,
    }
