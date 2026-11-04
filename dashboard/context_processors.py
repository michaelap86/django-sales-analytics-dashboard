from . import currency
from .roles import ADMIN, MANAGER, has_role, role_of


def app(request):
    user = request.user
    if not user.is_authenticated:
        return {}
    notifications = user.notifications.all()
    return {
        "role": role_of(user),
        "is_admin": has_role(user, ADMIN),
        "is_manager": has_role(user, MANAGER),
        "profile": getattr(user, "profile", None),
        "currency_code": currency.current(),
        "currency_symbol": currency.symbol(),
        "unread_count": notifications.filter(read=False).count(),
        "latest_notifications": notifications[:6],
    }
