"""Tests for sustained SOLAR eligibility helper."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from custom_components.energy_dispatcher.decision_helpers import update_solar_eligibility


def _t(minute: int = 0, second: int = 0) -> datetime:
    return datetime(2026, 7, 25, 12, minute, second, tzinfo=timezone.utc)


def test_sustain_not_ready_until_three_minutes() -> None:
    start = _t(0)
    since, ready, remaining = update_solar_eligibility(
        conditions_met=True,
        now=start,
        eligible_since=None,
        sustain_minutes=3,
    )
    assert since == start
    assert ready is False
    assert remaining == 180.0

    since2, ready2, remaining2 = update_solar_eligibility(
        conditions_met=True,
        now=start + timedelta(minutes=2, seconds=59),
        eligible_since=since,
        sustain_minutes=3,
    )
    assert since2 == start
    assert ready2 is False
    assert remaining2 == 1.0

    _, ready3, remaining3 = update_solar_eligibility(
        conditions_met=True,
        now=start + timedelta(minutes=3),
        eligible_since=since,
        sustain_minutes=3,
    )
    assert ready3 is True
    assert remaining3 == 0.0


def test_sustain_resets_when_conditions_drop() -> None:
    start = _t(0)
    since, _, _ = update_solar_eligibility(
        conditions_met=True,
        now=start,
        eligible_since=None,
        sustain_minutes=3,
    )
    since2, ready, remaining = update_solar_eligibility(
        conditions_met=False,
        now=start + timedelta(minutes=2),
        eligible_since=since,
        sustain_minutes=3,
    )
    assert since2 is None
    assert ready is False
    assert remaining == 0.0
