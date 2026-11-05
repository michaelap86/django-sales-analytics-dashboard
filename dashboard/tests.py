import io
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.db.models import F
from django.test import TestCase
from openpyxl import load_workbook

from . import demo
from .models import AuditLog, Customer, DailyTraffic, Notification, Order, Product, ScheduledReport


class DemoDataTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", orders=500, customers=120, months=26, stdout=io.StringIO())
        User = get_user_model()
        cls.admin = User.objects.get(username="demo")
        cls.manager = User.objects.get(username="manager")
        cls.viewer = User.objects.get(username="viewer")

    def setUp(self):
        self.client.force_login(self.admin)


class AuthTests(DemoDataTestCase):
    def setUp(self):
        pass

    def test_pages_require_login(self):
        response = self.client.get("/orders/")
        self.assertRedirects(response, "/login/?next=/orders/")

    def test_site_address_shows_the_login_form_without_redirect(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "password")
        self.client.post("/", {"username": "demo", "password": "demo1234"})
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_login_page_prefills_demo_account(self):
        response = self.client.get("/login/")
        self.assertContains(response, 'value="demo"')
        self.assertContains(response, 'value="demo1234"')

    def test_demo_credentials_work_and_are_audited(self):
        response = self.client.post("/login/", {"username": "demo", "password": "demo1234"})
        self.assertRedirects(response, "/")
        self.assertTrue(AuditLog.objects.filter(user=self.admin, action="login").exists())

    def test_team_members_cannot_sign_in(self):
        self.assertFalse(get_user_model().objects.get(username="sara.k").has_usable_password())


class PageTests(DemoDataTestCase):
    def test_every_page_renders(self):
        order = Order.objects.first()
        urls = [
            "/", "/?range=30d", "/?range=12m", "/?range=all", "/?range=bogus",
            "/?start=2020-01-01&end=2030-01-01&region=EU&status=refunded", "/?category=1&region=NA",
            "/orders/", "/orders/?category=2&q=a&sort=-total&page=2", "/orders/?sort=customer&page=999",
            f"/orders/{order.number}/",
            "/customers/", "/customers/?segment=vip&sort=-orders", "/customers/?q=a&region=EU&sort=last",
            f"/customers/{Customer.objects.first().pk}/",
            "/products/", "/products/?stock=low", "/products/?stock=out&sort=-sold",
            f"/products/{Product.objects.first().pk}/",
            "/reports/", "/reports/?range=30d&category=1", "/geography/", "/geography/?range=all",
            "/notifications/", "/notifications/?unread=1", "/notifications/?kind=stock",
            "/users/", "/audit-log/", "/audit-log/?action=login&q=demo", "/settings/",
            "/search/?q=", "/search/?q=SO-1", "/search/?q=laptop",
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_unknown_order_is_404(self):
        self.assertEqual(self.client.get("/orders/SO-0/").status_code, 404)

    def test_category_filter_does_not_inflate_totals(self):
        response = self.client.get("/orders/?range=all&category=1")
        for order in response.context["orders_page"]:
            self.assertEqual(order.total, sum(i.line_total for i in order.items.all()))

    def test_currency_preference_changes_amounts(self):
        self.admin.profile.currency = "EUR"
        self.admin.profile.save()
        self.assertContains(self.client.get("/"), "€")


class ExportTests(DemoDataTestCase):
    def test_excel_export(self):
        response = self.client.get("/orders/export.xlsx?range=all")
        ws = load_workbook(io.BytesIO(response.content)).active
        self.assertEqual(ws["A1"].value, "Order #")
        # header + one row per order + blank + totals row
        self.assertEqual(ws.max_row, Order.objects.count() + 3)

    def test_csv_exports(self):
        for url in ["/orders/export.csv?range=all", "/customers/export.csv", "/products/export.csv"]:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
                self.assertGreater(len(response.content.decode("utf-8-sig").splitlines()), 2)

    def test_pdfs(self):
        order = Order.objects.first()
        for url in [f"/orders/{order.number}/invoice.pdf", "/reports/export.pdf?range=90d"]:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response["Content-Type"], "application/pdf")
                self.assertTrue(response.content.startswith(b"%PDF"))

    def test_exports_are_audited(self):
        self.client.get("/customers/export.csv")
        self.assertTrue(AuditLog.objects.filter(action="export", target="Customers (CSV)").exists())


class RoleTests(DemoDataTestCase):
    def test_viewer_cannot_change_orders_or_stock_or_see_admin_pages(self):
        self.client.force_login(self.viewer)
        order = Order.objects.filter(status="paid").first() or Order.objects.filter(status="pending").first()
        product = Product.objects.first()
        self.assertEqual(self.client.post(f"/orders/{order.number}/status/", {"status": "refunded"}).status_code, 403)
        self.assertEqual(self.client.post(f"/products/{product.pk}/stock/", {"amount": 5}).status_code, 403)
        self.assertEqual(self.client.get("/users/").status_code, 403)
        self.assertEqual(self.client.get("/audit-log/").status_code, 403)

    def test_manager_changes_order_status(self):
        self.client.force_login(self.manager)
        order = Order.objects.filter(status="pending").first()
        self.client.post(f"/orders/{order.number}/status/", {"status": "paid", "note": "Paid by card"})
        order.refresh_from_db()
        self.assertEqual(order.status, "paid")
        self.assertTrue(order.events.filter(status="paid", user=self.manager).exists())
        self.assertTrue(AuditLog.objects.filter(action="order_status", target=order.number).exists())

    def test_invalid_transition_is_rejected(self):
        order = Order.objects.filter(status="delivered").first()
        self.client.post(f"/orders/{order.number}/status/", {"status": "pending"})
        order.refresh_from_db()
        self.assertEqual(order.status, "delivered")

    def test_low_stock_update_notifies_others(self):
        self.client.force_login(self.manager)
        product = Product.objects.first()
        before = Notification.objects.filter(user=self.admin, kind="stock").count()
        self.client.post(f"/products/{product.pk}/stock/", {"amount": 0, "mode": "set"})
        product.refresh_from_db()
        self.assertEqual(product.stock, 0)
        self.assertEqual(Notification.objects.filter(user=self.admin, kind="stock").count(), before + 1)

    def test_admin_changes_role_but_not_for_demo_accounts(self):
        target = get_user_model().objects.get(username="p.patel")
        self.client.post(f"/users/{target.pk}/role/", {"role": "Manager"})
        self.assertTrue(target.groups.filter(name="Manager").exists())
        self.client.post(f"/users/{self.viewer.pk}/role/", {"role": "Admin"})
        self.assertFalse(self.viewer.groups.filter(name="Admin").exists())


class DemoRefreshTests(TestCase):
    def setUp(self):
        call_command("seed_demo", orders=200, customers=60, months=6, stdout=io.StringIO())
        demo.__dict__["_checked_on"] = None

    def test_fresh_data_is_left_alone(self):
        first_order = Order.objects.order_by("pk").first().pk
        demo.refresh_if_stale()
        self.assertEqual(Order.objects.order_by("pk").first().pk, first_order)

    def test_stale_data_is_regenerated_without_signing_users_out(self):
        DailyTraffic.objects.update(date=F("date") - timedelta(days=3))
        user_pk = get_user_model().objects.get(username="demo").pk
        self.client.force_login(get_user_model().objects.get(username="demo"))

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)  # still signed in
        self.assertEqual(DailyTraffic.objects.latest("date").date, date.today())
        self.assertEqual(get_user_model().objects.get(username="demo").pk, user_pk)


class SettingsTests(DemoDataTestCase):
    def test_demo_password_cannot_change(self):
        self.client.post("/settings/", {"form": "password", "old_password": "demo1234",
                                        "new_password1": "Another-pass-99", "new_password2": "Another-pass-99"})
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.check_password("demo1234"))

    def test_scheduled_report_create_and_send(self):
        self.client.post("/settings/", {"form": "report", "name": "Test report", "frequency": "daily",
                                        "format": "csv", "recipients": "a@example.com, b@example.com"})
        report = ScheduledReport.objects.get(name="Test report")
        self.client.post(f"/settings/reports/{report.pk}/", {"action": "send"})
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["a@example.com", "b@example.com"])
        self.assertEqual(len(mail.outbox[0].attachments), 1)

    def test_send_scheduled_reports_command(self):
        out = io.StringIO()
        call_command("send_scheduled_reports", "--all", stdout=out)
        self.assertIn("3 report(s) sent", out.getvalue())
