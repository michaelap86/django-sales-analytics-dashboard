from django import template
from django.utils.http import urlencode
from django.utils.safestring import mark_safe

from .. import currency

register = template.Library()

# Lucide-style 24×24 stroke icons
ICONS = {
    "overview": '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
    "orders": '<path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4Z"/><path d="M3 6h18M16 10a4 4 0 0 1-8 0"/>',
    "customers": '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
    "products": '<path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="m3.3 7 8.7 5 8.7-5M12 22V12"/>',
    "reports": '<path d="M3 3v18h18"/><path d="M18 17V9M13 17V5M8 17v-3"/>',
    "geography": '<circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10Z"/>',
    "bell": '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
    "users": '<path d="M12 2 4 5v6c0 5 3.4 9.7 8 11 4.6-1.3 8-6 8-11V5Z"/><path d="m9 12 2 2 4-4"/>',
    "audit": '<path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5Z"/><path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z"/>',
    "search": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    "logout": '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>',
    "download": '<path d="M12 3v12m0 0-4-4m4 4 4-4M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/>',
    "file": '<path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5Z"/><path d="M14 2v6h6"/>',
    "menu": '<path d="M4 6h16M4 12h16M4 18h16"/>',
    "moon": '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    "revenue": '<path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>',
    "aov": '<path d="M3 3v18h18"/><path d="m7 15 4-4 3 3 5-6"/>',
    "profit": '<path d="M12 20V10M18 20V4M6 20v-4"/>',
    "alert": '<path d="m21.7 18-8-14a2 2 0 0 0-3.4 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.7-3Z"/><path d="M12 9v4M12 17h.01"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "refund": '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/>',
    "mail": '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-10 6L2 7"/>',
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
    "box": '<path d="M21 8v13H3V8M1 3h22v5H1zM10 12h4"/>',
    "truck": '<path d="M14 18V6a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v11a1 1 0 0 0 1 1h2M15 18H9M19 18h2a1 1 0 0 0 1-1v-3.65a1 1 0 0 0-.22-.62L18.3 8.38A1 1 0 0 0 17.52 8H14"/><circle cx="17" cy="18" r="2"/><circle cx="7" cy="18" r="2"/>',
    "card": '<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 10h20"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    "page": '<path d="M5 12h14M12 5l7 7-7 7"/>',
    "lock": '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
    "trend": '<path d="m22 7-8.5 8.5-5-5L2 17"/><path d="M16 7h6v6"/>',
    "edit": '<path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/>',
    "x": '<path d="M18 6 6 18M6 6l12 12"/>',
}

NOTIFICATION_ICONS = {"order": "orders", "stock": "alert", "refund": "refund", "report": "mail", "system": "info"}
STATUS_ICONS = {"pending": "clock", "paid": "card", "shipped": "truck", "delivered": "check", "refunded": "refund"}


@register.simple_tag
def icon(name, size=18):
    paths = ICONS.get(name, ICONS["info"])
    return mark_safe(
        f'<svg viewBox="0 0 24 24" width="{size}" height="{size}" aria-hidden="true">{paths}</svg>'
    )


@register.filter
def notification_icon(kind):
    return NOTIFICATION_ICONS.get(kind, "info")


@register.filter
def status_icon(status):
    return STATUS_ICONS.get(status, "info")


@register.filter
def money(value, decimals=0):
    """Format a USD amount in the viewer's preferred currency."""
    return f"{currency.symbol()}{currency.convert(value):,.{int(decimals)}f}"


@register.filter
def compact_money(value):
    v = float(currency.convert(value))
    for div, suffix in ((1e6, "M"), (1e3, "K")):
        if abs(v) >= div:
            return f"{currency.symbol()}{v / div:,.1f}{suffix}"
    return f"{currency.symbol()}{v:,.0f}"


@register.filter
def pct_of(value, total):
    try:
        return float(value) / float(total) * 100
    except (TypeError, ZeroDivisionError):
        return 0


@register.filter
def initials(name):
    parts = str(name).split()
    return "".join(p[0] for p in parts[:2]).upper()


@register.filter
def avatar_tone(pk):
    return int(pk or 0) % 6


@register.filter
def heat_level(value, peak):
    """0–1 intensity used as a CSS variable for heatmap cells."""
    try:
        return round(float(value) / float(peak), 3)
    except (TypeError, ZeroDivisionError):
        return 0


@register.filter
def retention_level(value):
    return round(min(float(value), 60) / 60, 3) if value is not None else 0


@register.filter
def get(mapping, key):
    return mapping.get(key) if mapping else None


@register.simple_tag(takes_context=True)
def sort_link(context, key):
    """Query string that sorts by `key`, flipping direction on a second click."""
    current = context["sort"] if "sort" in context else context["params"]["sort"]
    target = f"-{key}" if current == key else key
    if "filters" in context and context["filters"]:
        return context["filters"].querystring(sort=target)
    return urlencode({**context["base_params"], "sort": target})


@register.simple_tag(takes_context=True)
def sort_class(context, key):
    current = context["sort"] if "sort" in context else context["params"]["sort"]
    return "asc" if current == key else "desc" if current == f"-{key}" else ""


@register.simple_tag(takes_context=True)
def page_link(context, number):
    if "filters" in context and context["filters"]:
        return context["filters"].querystring(sort=context["sort"], page=number)
    params = dict(context.get("base_params") or context.get("params") or {})
    if "params" in context and "sort" in context["params"]:
        params["sort"] = context["params"]["sort"]
    params["page"] = number
    return urlencode({k: v for k, v in params.items() if v})


@register.simple_tag(takes_context=True)
def query_with(context, **kwargs):
    params = {**(context.get("base_params") or context.get("params") or {}), **kwargs}
    return urlencode({k: v for k, v in params.items() if v})
