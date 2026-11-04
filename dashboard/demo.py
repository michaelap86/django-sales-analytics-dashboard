"""Keep the demo data current.

The data is generated relative to "today". On hosts where the database
persists (unlike a container that is rebuilt on every start), the data would
slowly age and recent date filters would come up empty. The first request of
each day regenerates it.
"""

import io
import logging
import os
import time
from datetime import date

from django.conf import settings
from django.core.management import call_command
from django.db.models import Max

from .models import DailyTraffic

log = logging.getLogger(__name__)

_checked_on = None  # date of the last check in this process
LOCK_STALE_AFTER = 300  # seconds; a lock older than this is left over from a crash


def _lock_path():
    return settings.BASE_DIR / ".demo-refresh.lock"


def refresh_if_stale():
    """Regenerate the demo data when it was generated before today."""
    global _checked_on
    today = date.today()
    if _checked_on == today:
        return
    # Traffic has a row for every day up to the day the data was generated
    latest = DailyTraffic.objects.aggregate(latest=Max("date"))["latest"]
    if latest is not None and latest >= today:
        _checked_on = today
        return

    lock = _lock_path()
    try:
        if lock.exists() and time.time() - lock.stat().st_mtime > LOCK_STALE_AFTER:
            lock.unlink()
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return  # another worker is refreshing; serve the current data meanwhile
    try:
        os.close(fd)
        log.info("Demo data is from %s, regenerating", latest)
        call_command("seed_demo", stdout=io.StringIO())
        _checked_on = today
    finally:
        lock.unlink(missing_ok=True)


class DemoRefreshMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if settings.DEMO_AUTO_REFRESH:
            refresh_if_stale()
        return self.get_response(request)
