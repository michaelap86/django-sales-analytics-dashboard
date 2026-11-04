"""Sign-in, team & roles, audit log and personal settings."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.views import LoginView
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .. import scheduled
from ..activity import audit
from ..forms import PreferencesForm, ProfileForm, ScheduledReportForm
from ..models import AuditLog, ScheduledReport
from ..roles import ADMIN, ROLE_DESCRIPTIONS, ROLES, role_of, role_required, set_role

DEMO_ACCOUNTS = [
    ("demo", "Admin", "Everything, including users & audit log"),
    ("manager", "Manager", "Can update orders and stock"),
    ("viewer", "Viewer", "Read-only dashboards"),
]


class DemoLoginView(LoginView):
    template_name = "dashboard/login.html"
    redirect_authenticated_user = True

    def get_initial(self):
        # Pre-filled so visitors can sign in with one click
        return {"username": "demo"}

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["demo_accounts"] = DEMO_ACCOUNTS
        ctx["demo_password"] = settings.DEMO_PASSWORD
        return ctx


# ------------------------------------------------------------------ users

@role_required(ADMIN)
def users(request):
    User = get_user_model()
    people = User.objects.select_related("profile").prefetch_related("groups").annotate(
        actions=Count("auditlog", filter=Q(auditlog__action__in=[
            AuditLog.Action.ORDER_STATUS, AuditLog.Action.STOCK, AuditLog.Action.EXPORT])),
    ).order_by("-is_active", "first_name")
    rows = [{"user": u, "role": role_of(u)} for u in people]
    counts = {r: sum(1 for row in rows if row["role"] == r and row["user"].is_active) for r in ROLES}
    return render(request, "dashboard/users.html", {
        "page": "users",
        "rows": rows,
        "roles": [(r, ROLE_DESCRIPTIONS[r], counts[r]) for r in ROLES],
        "role_names": ROLES,
    })


@require_POST
@role_required(ADMIN)
def user_role(request, pk):
    target = get_object_or_404(get_user_model(), pk=pk)
    role = request.POST.get("role")
    if role not in ROLES:
        messages.error(request, "Unknown role.")
    elif target == request.user:
        messages.error(request, "You can't change your own role.")
    elif target.profile.is_demo:
        messages.error(request, "Demo accounts keep their roles so every visitor sees the same demo.")
    else:
        old = role_of(target)
        set_role(target, role)
        audit(request, AuditLog.Action.ROLE, target.username, f"{old} → {role}")
        messages.success(request, f"{target.get_full_name()} is now a {role}.")
    return redirect("users")


@require_POST
@role_required(ADMIN)
def user_active(request, pk):
    target = get_object_or_404(get_user_model(), pk=pk)
    if target == request.user or target.profile.is_demo:
        messages.error(request, "This account can't be deactivated.")
    else:
        target.is_active = not target.is_active
        target.save(update_fields=["is_active"])
        state = "Activated" if target.is_active else "Deactivated"
        audit(request, AuditLog.Action.USER_ACTIVE, target.username, state)
        messages.success(request, f"{state} {target.get_full_name()}.")
    return redirect("users")


# -------------------------------------------------------------- audit log

@role_required(ADMIN)
def audit_log(request):
    qs = AuditLog.objects.select_related("user")
    action = request.GET.get("action", "")
    user_id = request.GET.get("user", "")
    q = request.GET.get("q", "").strip()[:80]
    if action in AuditLog.Action.values:
        qs = qs.filter(action=action)
    if user_id.isdigit():
        qs = qs.filter(user_id=user_id)
    if q:
        qs = qs.filter(Q(target__icontains=q) | Q(details__icontains=q) | Q(ip__icontains=q))
    page = Paginator(qs, 25).get_page(request.GET.get("page"))
    params = {k: v for k, v in {"action": action, "user": user_id, "q": q}.items() if v}
    return render(request, "dashboard/audit_log.html", {
        "page": "audit",
        "log_page": page,
        "actions": AuditLog.Action.choices,
        "people": get_user_model().objects.order_by("first_name"),
        "params": params,
        "selected": {"action": action, "user": user_id, "q": q},
    })


# --------------------------------------------------------------- settings

def settings_view(request):
    user = request.user
    profile = user.profile
    forms = {
        "profile": ProfileForm(instance=user),
        "preferences": PreferencesForm(instance=profile),
        "password": PasswordChangeForm(user),
        "report": ScheduledReportForm(),
    }
    if request.method == "POST":
        which = request.POST.get("form")
        if which == "profile":
            form = forms["profile"] = ProfileForm(request.POST, instance=user)
            if form.is_valid():
                form.save()
                audit(request, AuditLog.Action.SETTINGS, user.username, "Updated profile")
                messages.success(request, "Profile saved.")
                return redirect("settings")
        elif which == "preferences":
            before = {f: getattr(profile, f) for f in ("currency", "timezone", "accent")}
            form = forms["preferences"] = PreferencesForm(request.POST, instance=profile)
            if form.is_valid():
                form.save()
                changes = ", ".join(f"{k} {before[k]} → {getattr(profile, k)}"
                                    for k in before if before[k] != getattr(profile, k))
                audit(request, AuditLog.Action.SETTINGS, user.username, changes or "No changes")
                messages.success(request, "Preferences saved.")
                return redirect("settings")
        elif which == "password":
            if profile.is_demo:
                messages.error(request, "Shared demo accounts can't change their password.")
                return redirect("settings")
            form = forms["password"] = PasswordChangeForm(user, request.POST)
            if form.is_valid():
                form.save()
                update_session_auth_hash(request, form.user)
                audit(request, AuditLog.Action.PASSWORD, user.username)
                messages.success(request, "Password changed.")
                return redirect("settings")
        elif which == "report":
            form = forms["report"] = ScheduledReportForm(request.POST)
            if form.is_valid():
                report = form.save(commit=False)
                report.user = user
                report.save()
                audit(request, AuditLog.Action.REPORT, report.name,
                      f"Created ({report.get_frequency_display()}, {report.get_format_display()})")
                messages.success(request, f"Scheduled \"{report.name}\".")
                return redirect("/settings/#reports")

    return render(request, "dashboard/settings.html", {
        "page": "settings",
        "forms": forms,
        "reports": user.reports.all(),
        "is_demo": profile.is_demo,
        "role_description": ROLE_DESCRIPTIONS[role_of(user)],
    })


@require_POST
def report_action(request, pk):
    report = get_object_or_404(ScheduledReport, pk=pk, user=request.user)
    action = request.POST.get("action")
    if action == "send":
        result = scheduled.send(report)
        audit(request, AuditLog.Action.REPORT, report.name, f"Sent to {len(result.recipients)} recipients")
        messages.success(request, f"\"{report.name}\" sent to {', '.join(result.recipients)}.")
    elif action == "toggle":
        report.active = not report.active
        report.save(update_fields=["active"])
        messages.success(request, f"\"{report.name}\" {'resumed' if report.active else 'paused'}.")
    elif action == "delete":
        audit(request, AuditLog.Action.REPORT, report.name, "Deleted")
        report.delete()
        messages.success(request, f"Deleted \"{report.name}\".")
    return redirect("/settings/#reports")
