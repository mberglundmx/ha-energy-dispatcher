"""Tests for the Energy Dispatcher decision engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from custom_components.energy_dispatcher.const import (
    ENERGY_MODE_GRID_CHEAP,
    ENERGY_MODE_SOLAR,
    GRID_STATE_CRITICAL,
    POWER_GUARD_STRATEGY_SIMPLE_THRESHOLD,
    REASON_DATA_UNAVAILABLE,
    REASON_GRID_EXPORT,
    REASON_NOT_CHEAP_YET,
    STATE_OFF,
    STATE_ON,
    STATE_UNKNOWN,
)
from custom_components.energy_dispatcher.decision_engine import evaluate_load
from custom_components.energy_dispatcher.models import (
    GlobalState,
    LoadConfig,
    PriceSlot,
    PriceThresholds,
    SourceRules,
)
from custom_components.energy_dispatcher.power_guard import PowerGuardState
from custom_components.energy_dispatcher.runtime_scheduler import RuntimeTracker


def _now() -> datetime:
    return datetime(2026, 7, 15, 10, 0, tzinfo=timezone.utc)


def _power_guard(**overrides) -> PowerGuardState:
    defaults = {
        "state": "NORMAL",
        "strategy": POWER_GUARD_STRATEGY_SIMPLE_THRESHOLD,
    }
    defaults.update(overrides)
    return PowerGuardState(**defaults)


def _global_state(**overrides) -> GlobalState:
    now = overrides.pop("now", _now())
    power_guard = overrides.pop("power_guard", _power_guard())
    base = GlobalState(
        now=now,
        grid_input=0.0,
        grid_output=0.0,
        export_price=0.05,
        price_timeline=(
            PriceSlot(start=now.replace(minute=0, second=0, microsecond=0), price=0.5),
            PriceSlot(
                start=now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=2),
                price=0.05,
            ),
        ),
        rolling_average_price=0.5,
        power_guard=power_guard,
        price_thresholds=PriceThresholds(
            free_threshold=0.02,
            cheap_ratio=0.3,
            expensive_ratio=1.5,
        ),
    )
    for key, value in overrides.items():
        object.__setattr__(base, key, value)
    return base


def _load(**overrides) -> LoadConfig:
    sources = overrides.pop("sources", SourceRules(solar_enabled=True, grid_cheap_enabled=True))
    required_power = overrides.pop("required_power", 1400)
    return LoadConfig(
        load_id="dehumidifier",
        name="Dehumidifier",
        required_power=required_power,
        sources=sources,
        **overrides,
    )


def test_grid_export_turns_load_on() -> None:
    decision = evaluate_load(
        _global_state(grid_output=2500),
        _load(),
        RuntimeTracker(),
    )
    assert decision.state == STATE_ON
    assert decision.energy_mode == ENERGY_MODE_SOLAR
    assert decision.reason == REASON_GRID_EXPORT
    assert decision.available_power == 2500


def test_no_export_falls_back_to_grid_cheap() -> None:
    now = _now()
    decision = evaluate_load(
        _global_state(
            now=now,
            grid_output=0,
            price_timeline=(
                PriceSlot(start=now.replace(minute=0, second=0, microsecond=0), price=0.05),
            ),
        ),
        _load(),
        RuntimeTracker(),
    )
    assert decision.state == STATE_ON
    assert decision.energy_mode == ENERGY_MODE_GRID_CHEAP


def test_off_with_next_opportunity_when_not_cheap_yet() -> None:
    now = _now()
    decision = evaluate_load(
        _global_state(
            now=now,
            grid_output=0,
            price_timeline=(
                PriceSlot(start=now.replace(minute=0, second=0, microsecond=0), price=0.5),
                PriceSlot(
                    start=now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=2),
                    price=0.05,
                ),
            ),
        ),
        _load(sources=SourceRules(grid_cheap_enabled=True)),
        RuntimeTracker(),
    )
    assert decision.state == STATE_OFF
    assert decision.reason == REASON_NOT_CHEAP_YET
    assert decision.next_opportunity is not None
    assert decision.energy_mode == ENERGY_MODE_GRID_CHEAP


def test_unknown_when_price_data_missing() -> None:
    decision = evaluate_load(
        _global_state(
            grid_output=0,
            price_timeline=(),
            export_price=None,
        ),
        _load(
            sources=SourceRules(
                solar_enabled=False,
                grid_free_enabled=True,
                grid_cheap_enabled=True,
                grid_normal_enabled=True,
                grid_expensive_enabled=True,
            )
        ),
        RuntimeTracker(),
    )
    assert decision.state == STATE_UNKNOWN
    assert decision.reason == REASON_DATA_UNAVAILABLE
    assert decision.price_state == "UNKNOWN"


def test_solar_still_works_without_price_timeline() -> None:
    decision = evaluate_load(
        _global_state(
            grid_output=2500,
            price_timeline=(),
            export_price=None,
        ),
        _load(),
        RuntimeTracker(),
    )
    assert decision.state == STATE_ON
    assert decision.energy_mode == ENERGY_MODE_SOLAR


def test_solar_hysteresis_keeps_on_while_still_exporting() -> None:
    """Once ON/SOLAR, stay on if export drops below required_power but remains > 0."""
    previous = evaluate_load(
        _global_state(grid_output=1500),
        _load(required_power=1000),
        RuntimeTracker(),
    )
    assert previous.state == STATE_ON
    assert previous.energy_mode == ENERGY_MODE_SOLAR

    decision = evaluate_load(
        _global_state(grid_output=500),
        _load(required_power=1000),
        RuntimeTracker(),
        previous=previous,
    )
    assert decision.state == STATE_ON
    assert decision.energy_mode == ENERGY_MODE_SOLAR
    assert decision.available_power == 500


def test_solar_stops_when_export_gone() -> None:
    previous = evaluate_load(
        _global_state(grid_output=1500),
        _load(required_power=1000),
        RuntimeTracker(),
    )
    assert previous.state == STATE_ON

    decision = evaluate_load(
        _global_state(
            grid_output=0,
            price_timeline=(
                PriceSlot(start=_now().replace(minute=0, second=0, microsecond=0), price=0.05),
            ),
        ),
        _load(required_power=1000),
        RuntimeTracker(),
        previous=previous,
    )
    assert decision.state == STATE_ON
    assert decision.energy_mode == ENERGY_MODE_GRID_CHEAP


def test_solar_does_not_start_below_required_power() -> None:
    decision = evaluate_load(
        _global_state(grid_output=500),
        _load(required_power=1000, sources=SourceRules(solar_enabled=True)),
        RuntimeTracker(),
    )
    assert decision.state != STATE_ON or decision.energy_mode != ENERGY_MODE_SOLAR


def test_power_guard_critical_forces_off() -> None:
    decision = evaluate_load(
        _global_state(
            grid_output=5000,
            power_guard=_power_guard(
                state=GRID_STATE_CRITICAL,
                current_import_power=12000,
                reason_text="Grid import power at critical level",
            ),
        ),
        _load(),
        RuntimeTracker(),
    )
    assert decision.state == STATE_OFF
