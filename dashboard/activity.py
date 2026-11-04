"""Audit log entries and in-app notifications."""

from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import AuditLog, Notification


def client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def audit(request, action, target="", details="", user=None):
    if user is None:
        current = getattr(request, "user", None)
        user = current if current is not None and current.is_authenticated else None
    return AuditLog.objects.create(
        user=user, action=action, target=str(target)[:120], details=str(details)[:255],
        ip=client_ip(request), created_at=timezone.now(),
    )


def notify_all(kind, title, body="", url="", exclude=None):
    """Send a notification to every active user (except `exclude`)."""
    users = get_user_model().objects.filter(is_active=True)
    if exclude is not None:
        users = users.exclude(pk=exclude.pk)
    now = timezone.now()
    Notification.objects.bulk_create([
        Notification(user=u, kind=kind, title=title, body=body, url=url, created_at=now)
        for u in users
    ])
