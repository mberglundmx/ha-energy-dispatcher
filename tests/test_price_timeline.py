"""Tests for price timeline slot selection and averages."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from custom_components.energy_dispatcher.const import ENERGY_MODE_GRID_CHEAP
from custom_components.energy_dispatcher.decision_helpers import classify_price
from custom_components.energy_dispatcher.models import (
    GlobalState,
    PriceSlot,
    PriceThresholds,
)
from custom_components.energy_dispatcher.power_guard import PowerGuardState
from custom_components.energy_dispatcher.price_timeline import (
    compute_rolling_average,
    current_slot,
    infer_slot_duration,
    list_slot_step,
)


def test_list_slot_step_detects_quarter_hour() -> None:
    assert list_slot_step(96) == timedelta(minutes=15)
    assert list_slot_step(24) == timedelta(hours=1)


def test_current_slot_uses_15_minute_window_not_stale_hour() -> None:
    """Regression: 1h window previously returned ~09:00 price at 10:02."""
    base = datetime(2026, 7, 24, 0, 0, tzinfo=timezone.utc)
    prices = [1.36 if i < 40 else 0.2 for i in range(96)]
    slots = tuple(
        PriceSlot(start=base + timedelta(minutes=15 * i), price=prices[i]) for i in range(96)
    )
    now = base.replace(hour=10, minute=2)
    assert infer_slot_duration(slots) == timedelta(minutes=15)
    slot = current_slot(slots, now)
    assert slot is not None
    assert slot.price == 0.2
    assert slot.start == base.replace(hour=10, minute=0)


def test_classify_0_2_as_cheap_with_today_average() -> None:
    prices = [
        1.37, 1.36, 1.35, 1.3, 1.34, 1.32, 1.32, 1.3, 1.32, 1.3, 1.25, 1.25, 1.3, 1.26,
        1.25, 1.1, 1.25, 1.24, 1.24, 1.15, 1.32, 1.28, 1.28, 1.34, 1.33, 1.33, 1.35, 1.35,
        1.36, 1.35, 1.28, 1.31, 1.37, 1.35, 1.09, 0.67, 1.36, 1.08, 0.42, 0.2, 0.3, 0.2,
        0.16, 0.14, 0.2, 0.18, 0.17, 0.15, 0.19, 0.16, 0.14, 0.12, 0.15, 0.14, 0.12, 0.11,
        0.1, 0.09, 0.1, 0.1, 0.08, 0.1, 0.11, 0.13, 0.1, 0.1, 0.11, 0.14, 0.13, 0.14, 0.17,
        0.28, 0.18, 0.41, 1.03, 1.28, 0.86, 0.97, 0.98, 1.25, 1.09, 1.09, 1.13, 1.12, 1.28,
        1.25, 1.25, 1.08, 1.3, 1.11, 0.77, 1.1, 1.31, 1.29, 1.08, 0.8,
    ]
    base = datetime(2026, 7, 24, 0, 0, tzinfo=timezone.utc)
    slots = tuple(
        PriceSlot(start=base + timedelta(minutes=15 * i), price=price)
        for i, price in enumerate(prices)
    )
    now = base.replace(hour=10, minute=2)
    current = current_slot(slots, now)
    assert current is not None
    assert current.price == 0.3  # 10:00 quarter in the provided series

    average = compute_rolling_average(slots, now)
    assert average is not None
    assert abs(average - sum(prices) / len(prices)) < 1e-9

    global_state = GlobalState(
        now=now,
        grid_input=0.0,
        grid_output=0.0,
        export_price=None,
        price_timeline=slots,
        rolling_average_price=average,
        power_guard=PowerGuardState(state="NORMAL", strategy="none"),
        price_thresholds=PriceThresholds(
            free_threshold=0.02,
            cheap_ratio=0.3,
            expensive_ratio=1.5,
        ),
    )
    # Midday 0.2 is cheap vs ~0.82 average. 0.3 at 10:00 is normal (~37% of avg).
    assert classify_price(0.2, global_state) == ENERGY_MODE_GRID_CHEAP
    assert classify_price(current.price, global_state) == "GRID_NORMAL"
