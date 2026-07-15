"""Runtime tracking and cheapest-slot scheduling for load requirements."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import math

from .const import REASON_RUNTIME_REQUIRED, STATE_OFF, STATE_ON
from .decision_helpers import (
    available_export_power,
    classify_price,
    is_mode_allowed,
    price_state,
)
from .models import Decision, GlobalState, LoadConfig, PriceSlot
from .price_timeline import current_slot


@dataclass
class RuntimeTracker:
    """Accumulated ON minutes for the current day and ISO week."""

    day_date: str = ""
    minutes_today: float = 0.0
    week_key: str = ""
    minutes_week: float = 0.0

    @classmethod
    def from_dict(cls, data: dict | None) -> RuntimeTracker:
        if not data:
            return cls()
        return cls(
            day_date=data.get("day_date", ""),
            minutes_today=float(data.get("minutes_today", 0.0)),
            week_key=data.get("week_key", ""),
            minutes_week=float(data.get("minutes_week", 0.0)),
        )

    def to_dict(self) -> dict:
        return {
            "day_date": self.day_date,
            "minutes_today": self.minutes_today,
            "week_key": self.week_key,
            "minutes_week": self.minutes_week,
        }


def remaining_runtime_minutes(load: LoadConfig, runtime: RuntimeTracker) -> float:
    """Return how many ON minutes are still required."""
    remaining = 0.0
    if load.minimum_minutes_per_day is not None:
        remaining = max(remaining, load.minimum_minutes_per_day - runtime.minutes_today)
    if load.minimum_minutes_per_week is not None:
        remaining = max(remaining, load.minimum_minutes_per_week - runtime.minutes_week)
    return max(0.0, remaining)


def accumulate_runtime(
    runtime: RuntimeTracker,
    now: datetime,
    interval_minutes: float,
    was_on: bool,
) -> RuntimeTracker:
    """Add elapsed ON minutes and roll over day/week boundaries."""
    day_date = now.date().isoformat()
    week_key = f"{now.isocalendar().year}-W{now.isocalendar().week:02d}"

    minutes_today = runtime.minutes_today if runtime.day_date == day_date else 0.0
    minutes_week = runtime.minutes_week if runtime.week_key == week_key else 0.0

    if was_on:
        minutes_today += interval_minutes
        minutes_week += interval_minutes

    return RuntimeTracker(
        day_date=day_date,
        minutes_today=minutes_today,
        week_key=week_key,
        minutes_week=minutes_week,
    )


def _window_end(now: datetime, load: LoadConfig, runtime: RuntimeTracker) -> datetime:
    """End of scheduling window based on active runtime constraints."""
    day_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    week_end = _week_end(now)

    needs_day = (
        load.minimum_minutes_per_day is not None
        and runtime.minutes_today < load.minimum_minutes_per_day
    )
    needs_week = (
        load.minimum_minutes_per_week is not None
        and runtime.minutes_week < load.minimum_minutes_per_week
    )

    if needs_week:
        return week_end
    return day_end


def _week_end(now: datetime) -> datetime:
    weekday = now.weekday()
    sunday = now + timedelta(days=6 - weekday)
    return sunday.replace(hour=23, minute=59, second=59, microsecond=999999)


def _eligible_runtime_slots(
    global_state: GlobalState,
    load: LoadConfig,
    window_end: datetime,
) -> list[tuple[PriceSlot, str]]:
    now = global_state.now
    hour_start = now.replace(minute=0, second=0, microsecond=0)
    slots: list[tuple[PriceSlot, str]] = []

    for slot in global_state.price_timeline:
        if slot.start < hour_start or slot.start > window_end:
            continue
        mode = classify_price(slot.price, global_state)
        if is_mode_allowed(mode, load.sources):
            slots.append((slot, mode))

    return slots


def select_cheapest_runtime_hours(
    global_state: GlobalState,
    load: LoadConfig,
    runtime: RuntimeTracker,
    remaining_minutes: float,
) -> list[tuple[PriceSlot, str]]:
    """Pick the cheapest allowed hours needed to cover remaining runtime."""
    if remaining_minutes <= 0:
        return []

    hours_needed = max(1, math.ceil(remaining_minutes / 60))
    window_end = _window_end(global_state.now, load, runtime)
    eligible = _eligible_runtime_slots(global_state, load, window_end)
    eligible.sort(key=lambda item: (item[0].price, item[0].start))
    return eligible[:hours_needed]


def evaluate_runtime_requirement(
    global_state: GlobalState,
    load: LoadConfig,
    runtime: RuntimeTracker,
    base_kwargs: dict,
) -> Decision | None:
    """Recommend ON during the cheapest hours needed to satisfy runtime."""
    remaining = remaining_runtime_minutes(load, runtime)
    if remaining <= 0:
        return None

    selected = select_cheapest_runtime_hours(
        global_state, load, runtime, remaining
    )
    if not selected:
        return None

    now = global_state.now
    current_hour = now.replace(minute=0, second=0, microsecond=0)
    selected_hours = {slot.start for slot, _mode in selected}
    current = current_slot(global_state.price_timeline, now)

    if current_hour in selected_hours:
        mode = next(
            (m for slot, m in selected if slot.start == current_hour),
            classify_price(current.price, global_state) if current else selected[0][1],
        )
        return Decision(
            state=STATE_ON,
            energy_mode=mode,
            reason=REASON_RUNTIME_REQUIRED,
            reason_text="Runtime requirement — cheapest allowed hour",
            next_opportunity=None,
            price_state=price_state(current, global_state),
            available_power=available_export_power(global_state),
            required_power=load.required_power,
            grid_state=base_kwargs["grid_state"],
        )

    future_hours = sorted(hour for hour in selected_hours if hour > now)
    if not future_hours:
        return None

    next_hour = future_hours[0]
    next_mode = next(mode for slot, mode in selected if slot.start == next_hour)
    return Decision(
        state=STATE_OFF,
        energy_mode=next_mode,
        reason=REASON_RUNTIME_REQUIRED,
        reason_text="Waiting for cheapest hour to satisfy runtime requirement",
        next_opportunity=next_hour,
        price_state=price_state(current, global_state),
        available_power=available_export_power(global_state),
        required_power=load.required_power,
        grid_state=base_kwargs["grid_state"],
    )
