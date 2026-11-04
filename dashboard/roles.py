"""Role-based access: Admin > Manager > Viewer, stored as Django groups."""

from functools import wraps

from django.core.exceptions import PermissionDenied

ADMIN, MANAGER, VIEWER = "Admin", "Manager", "Viewer"
ROLES = [ADMIN, MANAGER, VIEWER]
_RANK = {VIEWER: 1, MANAGER: 2, ADMIN: 3}

ROLE_DESCRIPTIONS = {
    ADMIN: "Full access, including users and the audit log",
    MANAGER: "Can update orders and inventory",
    VIEWER: "Read-only access to dashboards and exports",
}


def role_of(user):
    if not user.is_authenticated:
        return None
    if user.is_superuser:
        return ADMIN
    cached = getattr(user, "_role", None)
    if cached is None:
        names = set(user.groups.values_list("name", flat=True))
        cached = next((r for r in ROLES if r in names), VIEWER)
        user._role = cached
    return cached


def has_role(user, minimum):
    role = role_of(user)
    return role is not None and _RANK[role] >= _RANK[minimum]


def role_required(minimum):
    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not has_role(request.user, minimum):
                raise PermissionDenied(f"{minimum} role required")
            return view(request, *args, **kwargs)
        return wrapped
    return decorator


def set_role(user, role):
    from django.contrib.auth.models import Group

    user.groups.remove(*Group.objects.filter(name__in=ROLES))
    user.groups.add(Group.objects.get_or_create(name=role)[0])
    user._role = role
