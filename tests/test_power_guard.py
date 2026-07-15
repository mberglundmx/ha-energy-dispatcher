"""Tests for power guard strategies."""

from __future__ import annotations

from datetime import datetime, timezone

from custom_components.energy_dispatcher.const import (
    GRID_STATE_CRITICAL,
    GRID_STATE_NORMAL,
    GRID_STATE_WARNING,
    POWER_GUARD_STRATEGY_NONE,
    POWER_GUARD_STRATEGY_SIMPLE_THRESHOLD,
)
from custom_components.energy_dispatcher.hourly_aggregator import HourlyImportSnapshot
from custom_components.energy_dispatcher.power_guard import (
    PowerGuardConfig,
    evaluate_power_guard,
)


def _now(minute: int = 30) -> datetime:
    return datetime(2026, 7, 15, 10, minute, tzinfo=timezone.utc)


def _hourly(
    consumed_kwh: float,
    current_power_w: float | None,
    minute: int = 30,
) -> HourlyImportSnapshot:
    now = _now(minute)
    return HourlyImportSnapshot(
        hour_start=now.replace(minute=0, second=0, microsecond=0),
        consumed_kwh=consumed_kwh,
        current_power_w=current_power_w,
    )


def test_none_strategy_is_normal() -> None:
    state = evaluate_power_guard(
        PowerGuardConfig(strategy=POWER_GUARD_STRATEGY_NONE),
        _hourly(5.0, 10000),
        _now(),
    )
    assert state.state == GRID_STATE_NORMAL


def test_simple_threshold_critical_when_limit_reached() -> None:
    state = evaluate_power_guard(
        PowerGuardConfig(
            strategy=POWER_GUARD_STRATEGY_SIMPLE_THRESHOLD,
            hourly_limit_kwh=2.0,
        ),
        _hourly(consumed_kwh=2.0, current_power_w=1000),
        _now(),
    )
    assert state.state == GRID_STATE_CRITICAL
    assert state.current_hour_kwh == 2.0


def test_simple_threshold_warning_when_projected_to_exceed() -> None:
    # 1.0 kWh consumed, 30 min left, 3000 W → +1.5 kWh projected = 2.5 kWh total
    state = evaluate_power_guard(
        PowerGuardConfig(
            strategy=POWER_GUARD_STRATEGY_SIMPLE_THRESHOLD,
            hourly_limit_kwh=2.0,
        ),
        _hourly(consumed_kwh=1.0, current_power_w=3000, minute=30),
        _now(minute=30),
    )
    assert state.state == GRID_STATE_WARNING
    assert state.projected_hour_kwh == 2.5


def test_simple_threshold_normal_when_within_limit() -> None:
    # 0.5 kWh consumed, 3000 W for remaining 30 min → 0.5 + 1.5 = 2.0 kWh projected
    state = evaluate_power_guard(
        PowerGuardConfig(
            strategy=POWER_GUARD_STRATEGY_SIMPLE_THRESHOLD,
            hourly_limit_kwh=2.0,
        ),
        _hourly(consumed_kwh=0.5, current_power_w=3000, minute=30),
        _now(minute=30),
    )
    assert state.state == GRID_STATE_NORMAL
    assert state.projected_hour_kwh == 2.0
