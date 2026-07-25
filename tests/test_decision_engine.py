"""Tests for the Energy Dispatcher decision engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from custom_components.energy_dispatcher.const import (
    ENERGY_MODE_GRID_CHEAP,
    ENERGY_MODE_GRID_EXPENSIVE,
    ENERGY_MODE_SOLAR,
    GRID_STATE_CRITICAL,
    POWER_GUARD_STRATEGY_SIMPLE_THRESHOLD,
    POWER_LEARNING_FIXED,
    POWER_LEARNING_PENDING,
    POWER_LEARNING_READY,
    POWER_MODE_FIXED,
    POWER_MODE_SENSOR,
    REASON_DATA_UNAVAILABLE,
    REASON_GRID_EXPORT,
    REASON_NOT_CHEAP_YET,
    STATE_OFF,
    STATE_ON,
    STATE_UNKNOWN,
)
from custom_components.energy_dispatcher.decision_engine import evaluate_load
from custom_components.energy_dispatcher.models import (
    Decision,
    GlobalState,
    LoadConfig,
    LoadPowerSnapshot,
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
    power_mode = overrides.pop("power_mode", POWER_MODE_FIXED)
    return LoadConfig(
        load_id="dehumidifier",
        name="Dehumidifier",
        power_mode=power_mode,
        required_power=required_power,
        sources=sources,
        **overrides,
    )


def _power(
    *,
    required: float | None,
    measured: float = 0.0,
    mode: str = POWER_MODE_FIXED,
    learning: str = POWER_LEARNING_FIXED,
) -> LoadPowerSnapshot:
    return LoadPowerSnapshot(
        power_mode=mode,
        power_learning=learning,
        effective_required_power=required,
        measured_power=measured,
        learned_required_power=required if learning == POWER_LEARNING_READY else None,
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


def test_solar_hysteresis_uses_export_plus_measured() -> None:
    """While ON at full draw, residual export still covers rated power."""
    previous = evaluate_load(
        _global_state(grid_output=1500),
        _load(required_power=1000),
        RuntimeTracker(),
        power=_power(required=1000, measured=0),
    )
    assert previous.state == STATE_ON
    assert previous.energy_mode == ENERGY_MODE_SOLAR

    decision = evaluate_load(
        _global_state(grid_output=500),
        _load(required_power=1000),
        RuntimeTracker(),
        previous=previous,
        power=_power(required=1000, measured=1000),
    )
    assert decision.state == STATE_ON
    assert decision.energy_mode == ENERGY_MODE_SOLAR
    assert decision.available_power == 500


def test_solar_rejects_low_draw_without_headroom_for_full_power() -> None:
    """ON at 10W with only 100W export must not claim SOLAR for 1000W rated load."""
    previous = Decision(
        state=STATE_ON,
        energy_mode=ENERGY_MODE_GRID_CHEAP,
        reason="grid_cheap",
        reason_text="cheap",
        available_power=100,
        required_power=1000,
        price_state="LOW",
        grid_state="NORMAL",
    )
    decision = evaluate_load(
        _global_state(grid_output=100),
        _load(required_power=1000, sources=SourceRules(solar_enabled=True)),
        RuntimeTracker(),
        previous=previous,
        power=_power(
            required=1000,
            measured=10,
            mode=POWER_MODE_SENSOR,
            learning=POWER_LEARNING_READY,
        ),
    )
    assert decision.energy_mode != ENERGY_MODE_SOLAR


def test_solar_switches_from_grid_when_headroom_covers_full_power() -> None:
    previous = Decision(
        state=STATE_ON,
        energy_mode=ENERGY_MODE_GRID_EXPENSIVE,
        reason="grid_expensive",
        reason_text="expensive",
        available_power=0,
        required_power=1100,
        price_state="HIGH",
        grid_state="NORMAL",
    )
    decision = evaluate_load(
        _global_state(grid_output=1033),
        _load(required_power=1100),
        RuntimeTracker(),
        previous=previous,
        power=_power(required=1100, measured=1100),
    )
    assert decision.state == STATE_ON
    assert decision.energy_mode == ENERGY_MODE_SOLAR
    assert decision.reason == REASON_GRID_EXPORT


def test_solar_cold_start_chances_when_exporting() -> None:
    decision = evaluate_load(
        _global_state(grid_output=200),
        _load(power_mode=POWER_MODE_SENSOR, required_power=None, power_sensor="sensor.x"),
        RuntimeTracker(),
        power=_power(
            required=None,
            measured=0,
            mode=POWER_MODE_SENSOR,
            learning=POWER_LEARNING_PENDING,
        ),
    )
    assert decision.state == STATE_ON
    assert decision.energy_mode == ENERGY_MODE_SOLAR


def test_solar_stops_when_export_gone() -> None:
    previous = evaluate_load(
        _global_state(grid_output=1500),
        _load(required_power=1000),
        RuntimeTracker(),
        power=_power(required=1000, measured=0),
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
        power=_power(required=1000, measured=1000),
    )
    assert decision.state == STATE_ON
    assert decision.energy_mode == ENERGY_MODE_GRID_CHEAP


def test_solar_does_not_start_below_required_power() -> None:
    decision = evaluate_load(
        _global_state(grid_output=500),
        _load(required_power=1000, sources=SourceRules(solar_enabled=True)),
        RuntimeTracker(),
        power=_power(required=1000, measured=0),
    )
    assert decision.state != STATE_ON or decision.energy_mode != ENERGY_MODE_SOLAR


def test_solar_entry_waits_for_sustain() -> None:
    decision = evaluate_load(
        _global_state(grid_output=2500),
        _load(),
        RuntimeTracker(),
        power=_power(required=1400, measured=0),
        solar_entry_ready=False,
    )
    assert decision.energy_mode != ENERGY_MODE_SOLAR


def test_solar_keep_skips_sustain_when_already_solar() -> None:
    previous = Decision(
        state=STATE_ON,
        energy_mode=ENERGY_MODE_SOLAR,
        reason=REASON_GRID_EXPORT,
        reason_text="keep",
        available_power=500,
        required_power=1000,
        price_state="LOW",
        grid_state="NORMAL",
    )
    decision = evaluate_load(
        _global_state(grid_output=500),
        _load(required_power=1000),
        RuntimeTracker(),
        previous=previous,
        power=_power(required=1000, measured=1000),
        solar_entry_ready=False,
    )
    assert decision.state == STATE_ON
    assert decision.energy_mode == ENERGY_MODE_SOLAR


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
