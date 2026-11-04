"""Display currency for the current request.

All amounts are stored in USD; the user's preferred currency is applied only
when rendering. Rates are fixed because the data is fictional.
"""

from contextvars import ContextVar
from decimal import Decimal

RATES = {"USD": Decimal("1"), "EUR": Decimal("0.92"), "GBP": Decimal("0.79")}
SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£"}

_current = ContextVar("currency", default="USD")


def activate(code):
    _current.set(code if code in RATES else "USD")


def current():
    return _current.get()


def convert(amount):
    return Decimal(amount or 0) * RATES[current()]


def as_float(amount):
    return float(convert(amount))


def symbol():
    return SYMBOLS[current()]
