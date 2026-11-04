"""Send every scheduled report that is due. Run it hourly from cron or a scheduler."""

from django.core.management.base import BaseCommand

from dashboard.models import ScheduledReport
from dashboard.scheduled import is_due, send


class Command(BaseCommand):
    help = "E-mail scheduled reports that are due."

    def add_arguments(self, parser):
        parser.add_argument("--all", action="store_true", help="Send every active report now.")

    def handle(self, *args, **opts):
        sent = 0
        for report in ScheduledReport.objects.select_related("user__profile").filter(active=True):
            if opts["all"] or is_due(report):
                result = send(report)
                sent += 1
                self.stdout.write(f"Sent '{report.name}' to {', '.join(result.recipients)}")
        self.stdout.write(self.style.SUCCESS(f"{sent} report(s) sent."))
