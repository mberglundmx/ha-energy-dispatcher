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


def list_slot_step(count: int) -> timedelta:
    """Guess slot length for plain numeric day lists (24 hourly / 96 quarter-hour)."""
    if count <= 0:
        return timedelta(hours=1)
    if count == 24:
        return timedelta(hours=1)
    if count == 96:
        return timedelta(minutes=15)
    if count % 24 == 0 and count > 24:
        minutes = (24 * 60) // count
        if minutes > 0 and (24 * 60) % count == 0:
            return timedelta(minutes=minutes)
    return timedelta(hours=1)


def infer_slot_duration(slots: tuple[PriceSlot, ...] | list[PriceSlot]) -> timedelta:
    """Infer slot length from gaps between consecutive starts (median)."""
    if len(slots) < 2:
        return timedelta(hours=1)
    gaps = [
        slots[i + 1].start - slots[i].start
        for i in range(len(slots) - 1)
        if slots[i + 1].start > slots[i].start
    ]
    if not gaps:
        return timedelta(hours=1)
    gaps.sort()
    return gaps[len(gaps) // 2]


def current_slot(slots: tuple[PriceSlot, ...], now: datetime) -> PriceSlot | None:
    """Return the price slot covering *now* (supports hourly and 15‑minute data)."""
    if not slots:
        return None

    duration = infer_slot_duration(slots)
    matching: PriceSlot | None = None
    for slot in slots:
        if slot.start <= now < slot.start + duration:
            # Keep the latest matching start (correct for sub-hourly slots).
            matching = slot
    if matching is not None:
        return matching

    started = [slot for slot in slots if slot.start <= now]
    if started:
        return started[-1]
    return slots[0]
