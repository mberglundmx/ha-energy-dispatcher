"""Price timeline helpers without Home Assistant dependencies."""

from __future__ import annotations

from datetime import datetime, timedelta

from .models import PriceSlot


def compute_rolling_average(slots: tuple[PriceSlot, ...], now: datetime) -> float | None:
    """Compute a rolling weekly average from available timeline data."""
    if not slots:
        return None
    week_ago = now - timedelta(days=7)
    recent = [slot.price for slot in slots if slot.start >= week_ago]
    if not recent:
        recent = [slot.price for slot in slots]
    if not recent:
        return None
    return sum(recent) / len(recent)


def current_slot(slots: tuple[PriceSlot, ...], now: datetime) -> PriceSlot | None:
    """Return the price slot covering the current hour."""
    hour_start = now.replace(minute=0, second=0, microsecond=0)
    for slot in slots:
        if slot.start == hour_start:
            return slot
    for slot in slots:
        if slot.start <= now < slot.start + timedelta(hours=1):
            return slot
    return slots[0] if slots else None
