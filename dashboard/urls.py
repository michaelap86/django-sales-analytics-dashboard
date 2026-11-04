from django.contrib.auth.views import LogoutView
from django.urls import path

from .views import customers, notifications, orders, overview, products, reports, search, system

urlpatterns = [
    path("", overview.dashboard, name="dashboard"),
    path("login/", system.DemoLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),

    path("reports/", reports.reports, name="reports"),
    path("reports/export.pdf", reports.report_pdf, name="report_pdf"),
    path("geography/", reports.geography, name="geography"),

    path("orders/", orders.orders, name="orders"),
    path("orders/export.xlsx", orders.export_orders, name="export_orders"),
    path("orders/export.csv", orders.export_orders_csv, name="export_orders_csv"),
    path("orders/<str:number>/", orders.order_detail, name="order_detail"),
    path("orders/<str:number>/status/", orders.order_status, name="order_status"),
    path("orders/<str:number>/invoice.pdf", orders.invoice_pdf, name="invoice_pdf"),

    path("customers/", customers.customers, name="customers"),
    path("customers/export.csv", customers.export_customers_csv, name="export_customers_csv"),
    path("customers/<int:pk>/", customers.customer_detail, name="customer_detail"),

    path("products/", products.products, name="products"),
    path("products/export.csv", products.export_products_csv, name="export_products_csv"),
    path("products/<int:pk>/", products.product_detail, name="product_detail"),
    path("products/<int:pk>/stock/", products.product_stock, name="product_stock"),

    path("search/", search.search, name="search"),
    path("notifications/", notifications.notifications, name="notifications"),
    path("notifications/read-all/", notifications.read_all, name="notifications_read_all"),
    path("notifications/<int:pk>/", notifications.open_notification, name="open_notification"),

    path("users/", system.users, name="users"),
    path("users/<int:pk>/role/", system.user_role, name="user_role"),
    path("users/<int:pk>/active/", system.user_active, name="user_active"),
    path("audit-log/", system.audit_log, name="audit_log"),
    path("settings/", system.settings_view, name="settings"),
    path("settings/reports/<int:pk>/", system.report_action, name="report_action"),
]
