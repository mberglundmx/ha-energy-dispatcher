"""Tests for hourly import aggregation."""

from __future__ import annotations

from datetime import datetime, timezone

from custom_components.energy_dispatcher.hourly_aggregator import (
    HourlyAggregator,
    projected_hour_kwh,
)


def _dt(hour: int, minute: int) -> datetime:
    return datetime(2026, 7, 15, hour, minute, tzinfo=timezone.utc)


def test_aggregator_integrates_power_over_time() -> None:
    aggregator = HourlyAggregator()

    first = aggregator.update(2000, _dt(10, 0))
    assert first.consumed_kwh == 0.0

    second = aggregator.update(2000, _dt(10, 30))
    assert second.consumed_kwh == 1.0

    projected = projected_hour_kwh(second, _dt(10, 30))
    assert projected == 2.0


def test_aggregator_resets_on_new_hour() -> None:
    aggregator = HourlyAggregator()
    aggregator.update(3000, _dt(10, 45))
    snapshot = aggregator.update(3000, _dt(11, 0))
    assert snapshot.consumed_kwh == 0.0
