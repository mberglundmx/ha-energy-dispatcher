"""Tests for runtime scheduling."""

from __future__ import annotations

from datetime import datetime, timezone

from custom_components.energy_dispatcher.const import REASON_RUNTIME_REQUIRED, STATE_ON
from custom_components.energy_dispatcher.decision_engine import evaluate_load
from custom_components.energy_dispatcher.models import (
    GlobalState,
    LoadConfig,
    PriceSlot,
    PriceThresholds,
    SourceRules,
)
from custom_components.energy_dispatcher.power_guard import PowerGuardState
from custom_components.energy_dispatcher.runtime_scheduler import (
    RuntimeTracker,
    select_cheapest_runtime_hours,
)


def _now(hour: int = 10) -> datetime:
    return datetime(2026, 7, 15, hour, 0, tzinfo=timezone.utc)


def _state(now: datetime, timeline: tuple[PriceSlot, ...]) -> GlobalState:
    return GlobalState(
        now=now,
        grid_input=0.0,
        grid_output=0.0,
        export_price=0.05,
        price_timeline=timeline,
        rolling_average_price=0.5,
        power_guard=PowerGuardState(state="NORMAL", strategy="none"),
        price_thresholds=PriceThresholds(0.02, 0.3, 1.5),
    )


def test_selects_cheapest_hours_for_remaining_runtime() -> None:
    now = _now(10)
    timeline = (
        PriceSlot(start=_now(10), price=0.40),
        PriceSlot(start=_now(14), price=0.05),
        PriceSlot(start=_now(18), price=0.30),
    )
    load = LoadConfig(
        load_id="pump",
        name="Pump",
        required_power=1000,
        minimum_minutes_per_day=120,
        sources=SourceRules(grid_cheap_enabled=True),
    )
    runtime = RuntimeTracker(day_date="2026-07-15", minutes_today=0.0)

    selected = select_cheapest_runtime_hours(_state(now, timeline), load, runtime, 120)
    assert len(selected) == 1
    assert selected[0][0].start == _now(14)


def test_runtime_turns_on_during_cheapest_selected_hour() -> None:
    now = _now(14)
    timeline = (
        PriceSlot(start=_now(10), price=0.40),
        PriceSlot(start=_now(14), price=0.05),
        PriceSlot(start=_now(18), price=0.30),
    )
    load = LoadConfig(
        load_id="pump",
        name="Pump",
        required_power=1000,
        minimum_minutes_per_day=120,
        sources=SourceRules(solar_enabled=False, grid_cheap_enabled=True),
    )
    runtime = RuntimeTracker(day_date="2026-07-15", minutes_today=0.0)
    base_kwargs = {
        "available_power": 0.0,
        "required_power": 1000,
        "price_state": "LOW",
        "grid_state": "NORMAL",
    }

    from custom_components.energy_dispatcher.runtime_scheduler import (
        evaluate_runtime_requirement,
    )

    decision = evaluate_runtime_requirement(
        _state(now, timeline), load, runtime, base_kwargs
    )
    assert decision.state == STATE_ON
    assert decision.reason == REASON_RUNTIME_REQUIRED
