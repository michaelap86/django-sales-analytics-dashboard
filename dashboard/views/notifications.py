from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from ..models import Notification


def notifications(request):
    qs = request.user.notifications.all()
    kind = request.GET.get("kind", "")
    if kind in Notification.Kind.values:
        qs = qs.filter(kind=kind)
    if request.GET.get("unread"):
        qs = qs.filter(read=False)
    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    return render(request, "dashboard/notifications.html", {
        "page": "notifications",
        "notifications_page": page,
        "kinds": Notification.Kind.choices,
        "kind": kind,
        "unread_only": bool(request.GET.get("unread")),
    })


def open_notification(request, pk):
    note = get_object_or_404(Notification, pk=pk, user=request.user)
    if not note.read:
        note.read = True
        note.save(update_fields=["read"])
    if note.url and url_has_allowed_host_and_scheme(note.url, allowed_hosts={request.get_host()}):
        return redirect(note.url)
    return redirect("notifications")


@require_POST
def read_all(request):
    request.user.notifications.filter(read=False).update(read=True)
    target = request.POST.get("next", "")
    if url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return redirect(target)
    return redirect("notifications")
