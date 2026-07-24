"""Tests for load power peak learning."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from custom_components.energy_dispatcher.power_learner import (
    BLOCK_MINUTES,
    LoadPowerLearner,
    PowerPeak,
)


def _t(minute: int = 0) -> datetime:
    return datetime(2026, 7, 24, 10, minute, tzinfo=timezone.utc)


def test_learns_block_average_after_five_minutes() -> None:
    learner = LoadPowerLearner()
    start = _t(0)
    assert learner.sample(start, 900.0, is_on=True) is False
    assert learner.learned_required_power(start) is None

    for minute in range(1, 5):
        assert learner.sample(start + timedelta(minutes=minute), 1100.0, is_on=True) is False

    changed = learner.sample(start + timedelta(minutes=BLOCK_MINUTES), 1000.0, is_on=True)
    assert changed is True
    learned = learner.learned_required_power(start + timedelta(minutes=BLOCK_MINUTES))
    assert learned is not None
    assert 1000 <= learned <= 1100


def test_ignores_idle_block_average() -> None:
    learner = LoadPowerLearner()
    start = _t(0)
    learner.sample(start, 5.0, is_on=True)
    changed = learner.sample(start + timedelta(minutes=BLOCK_MINUTES), 5.0, is_on=True)
    assert changed is False
    assert learner.learned_required_power(start) is None


def test_prunes_peaks_older_than_seven_days() -> None:
    now = _t(0)
    learner = LoadPowerLearner(
        peaks=[
            PowerPeak(at=now - timedelta(days=8), watts=1500),
            PowerPeak(at=now - timedelta(days=1), watts=900),
        ]
    )
    assert learner.learned_required_power(now) == 900
