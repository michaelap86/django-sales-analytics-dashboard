"""Parse the filter bar (query string) shared by every page."""

from dataclasses import dataclass, field
from datetime import date, timedelta

from django.db.models import Max, Min, Q
from django.utils.http import urlencode

from .models import Category, Order, OrderItem, Region

PRESETS = {
    "30d": ("Last 30 days", 30),
    "90d": ("Last 90 days", 90),
    "12m": ("Last 12 months", 365),
    "all": ("All time", None),
}
DEFAULT_PRESET = "90d"


def _parse_date(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


@dataclass
class Filters:
    start: date
    end: date
    preset: str
    category: Category | None = None
    region: str = ""
    status: str = ""
    q: str = ""
    params: dict = field(default_factory=dict)

    @property
    def days(self):
        return (self.end - self.start).days + 1

    @property
    def previous(self):
        """The equally long period right before this one."""
        prev_end = self.start - timedelta(days=1)
        return prev_end - timedelta(days=self.days - 1), prev_end

    @property
    def label(self):
        if self.preset in PRESETS:
            return PRESETS[self.preset][0]
        return f"{self.start:%b %d, %Y} – {self.end:%b %d, %Y}"

    def querystring(self, **overrides):
        params = {**self.params, **overrides}
        return urlencode({k: v for k, v in params.items() if v})

    def apply_to_items(self, qs, start=None, end=None):
        qs = qs.filter(
            order__created__gte=start or self.start,
            order__created__lte=end or self.end,
        )
        return self.apply_dimensions(qs)

    def apply_dimensions(self, qs):
        """Category/region/status filters on an OrderItem queryset, without dates."""
        if self.category:
            qs = qs.filter(product__category=self.category)
        if self.region:
            qs = qs.filter(order__customer__region=self.region)
        if self.status:
            qs = qs.filter(order__status=self.status)
        else:
            qs = qs.exclude(order__status=Order.Status.REFUNDED)
        return qs

    def apply_to_orders(self, qs):
        qs = qs.filter(created__gte=self.start, created__lte=self.end)
        if self.category:
            # Subquery instead of a join, so annotated order totals aren't multiplied
            qs = qs.filter(pk__in=OrderItem.objects.filter(
                product__category=self.category).values("order"))
        if self.region:
            qs = qs.filter(customer__region=self.region)
        if self.status:
            qs = qs.filter(status=self.status)
        if self.q:
            qs = qs.filter(
                Q(number__icontains=self.q)
                | Q(customer__name__icontains=self.q)
                | Q(customer__email__icontains=self.q)
                | Q(customer__company__icontains=self.q)
            )
        return qs


def parse_filters(request):
    get = request.GET
    bounds = Order.objects.aggregate(first=Min("created"), last=Max("created"))
    last = bounds["last"] or date.today()
    first = bounds["first"] or last

    preset = get.get("range", DEFAULT_PRESET)
    start, end = _parse_date(get.get("start")), _parse_date(get.get("end"))
    if start and end and start <= end:
        preset = "custom"
    else:
        if preset not in PRESETS:
            preset = DEFAULT_PRESET
        end = last
        days = PRESETS[preset][1]
        start = first if days is None else end - timedelta(days=days - 1)

    category = Category.objects.filter(pk=get.get("category")).first() if get.get("category", "").isdigit() else None
    region = get.get("region", "") if get.get("region") in Region.values else ""
    status = get.get("status", "") if get.get("status") in Order.Status.values else ""
    q = get.get("q", "").strip()[:80]

    params = {
        "range": preset if preset != "custom" else "",
        "start": start.isoformat() if preset == "custom" else "",
        "end": end.isoformat() if preset == "custom" else "",
        "category": category.pk if category else "",
        "region": region,
        "status": status,
        "q": q,
    }
    return Filters(start, end, preset, category, region, status, q, params)
