"""Small helpers shared by the workflows."""

from __future__ import annotations

import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

_ENTITY_SUFFIXES = {"llc", "pllc", "inc", "pa", "pc", "ltd", "co", "lp", "llp", "the"}


def provider_key(name: str | None) -> str:
    """Normalize a provider name so "Metro Pain & Spine" and "Metro Pain and Spine, PLLC" match."""
    text = (name or "").casefold().replace("&", " and ")
    words = re.sub(r"[^a-z0-9 ]", " ", text).split()
    return " ".join(w for w in words if w not in _ENTITY_SUFFIXES)


def to_date(value) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def money(value) -> Decimal:
    """Round to cents, half up, the way a person rounds currency."""
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def fmt_money(value) -> str:
    return f"${money(value):,.2f}"
