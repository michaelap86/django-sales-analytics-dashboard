from django.db.models import Q
from django.shortcuts import render
from django.urls import reverse

from ..models import Customer, Order, Product
from ..roles import ADMIN, has_role

PAGES = [
    ("Overview", "dashboard", "Sales KPIs and charts", None),
    ("Reports", "reports", "Cohorts, funnel, forecast, year over year", None),
    ("Geography", "geography", "Sales by country and region", None),
    ("Orders", "orders", "All orders", None),
    ("Customers", "customers", "Customer list and segments", None),
    ("Products", "products", "Catalogue and inventory", None),
    ("Notifications", "notifications", "Your alerts", None),
    ("Settings", "settings", "Profile, preferences, scheduled reports", None),
    ("Users & roles", "users", "Manage team access", ADMIN),
    ("Audit log", "audit_log", "Who changed what", ADMIN),
]


def search(request):
    """HTML fragment for the Ctrl+K command palette."""
    q = request.GET.get("q", "").strip()[:80]
    groups = []
    pages = [
        {"title": t, "url": reverse(name), "sub": sub}
        for t, name, sub, role in PAGES
        if (role is None or has_role(request.user, role)) and (not q or q.lower() in t.lower())
    ]
    if q:
        orders = Order.objects.with_totals().select_related("customer").filter(
            Q(number__icontains=q) | Q(customer__name__icontains=q))[:5]
        customers = Customer.objects.filter(
            Q(name__icontains=q) | Q(email__icontains=q) | Q(company__icontains=q))[:5]
        products = Product.objects.select_related("category").filter(
            Q(name__icontains=q) | Q(sku__icontains=q))[:5]
        if orders:
            groups.append(("Orders", "order", [
                {"title": o.number, "url": reverse("order_detail", args=[o.number]),
                 "sub": f"{o.customer.name} · {o.created:%b %d, %Y}", "total": o.total,
                 "status": o.status, "status_label": o.get_status_display()}
                for o in orders]))
        if customers:
            groups.append(("Customers", "customer", [
                {"title": c.name, "url": reverse("customer_detail", args=[c.pk]),
                 "sub": f"{c.company or 'Individual'} · {c.email}"}
                for c in customers]))
        if products:
            groups.append(("Products", "product", [
                {"title": p.name, "url": reverse("product_detail", args=[p.pk]),
                 "sub": f"{p.sku} · {p.category.name} · {p.stock} in stock"}
                for p in products]))
    if pages:
        groups.append(("Pages", "page", pages[:6]))
    return render(request, "dashboard/_search_results.html", {"groups": groups, "q": q})
