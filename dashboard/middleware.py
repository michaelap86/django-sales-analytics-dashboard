import zoneinfo

from django.utils import timezone

from . import currency


class UserPreferencesMiddleware:
    """Activate the signed-in user's currency and time zone for this request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        profile = getattr(request.user, "profile", None) if request.user.is_authenticated else None
        currency.activate(profile.currency if profile else "USD")
        try:
            timezone.activate(zoneinfo.ZoneInfo(profile.timezone if profile else "UTC"))
        except zoneinfo.ZoneInfoNotFoundError:
            timezone.deactivate()
        return self.get_response(request)
