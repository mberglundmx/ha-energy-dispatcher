"""Hourly grid import aggregation without Home Assistant dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class HourlyImportSnapshot:
    """Grid import energy accumulated for the current clock hour."""

    hour_start: datetime
    consumed_kwh: float
    current_power_w: float | None


class HourlyAggregator:
    """Integrate grid import power (W) into hourly kWh totals."""

    def __init__(self) -> None:
        self._hour_start: datetime | None = None
        self._consumed_kwh = 0.0
        self._last_sample: datetime | None = None
        self._last_power_w: float | None = None

    def update(self, power_w: float | None, now: datetime) -> HourlyImportSnapshot:
        """Record a sample and return the current hour snapshot."""
        hour_start = now.replace(minute=0, second=0, microsecond=0)
        if self._hour_start != hour_start:
            self._reset_hour(hour_start)

        if (
            power_w is not None
            and self._last_sample is not None
            and self._last_power_w is not None
        ):
            dt_hours = (now - self._last_sample).total_seconds() / 3600
            if dt_hours > 0:
                average_power_w = (self._last_power_w + power_w) / 2
                self._consumed_kwh += (average_power_w / 1000) * dt_hours

        if power_w is not None:
            self._last_sample = now
            self._last_power_w = power_w

        return HourlyImportSnapshot(
            hour_start=hour_start,
            consumed_kwh=self._consumed_kwh,
            current_power_w=power_w,
        )

    def _reset_hour(self, hour_start: datetime) -> None:
        self._hour_start = hour_start
        self._consumed_kwh = 0.0
        self._last_sample = None
        self._last_power_w = None


def projected_hour_kwh(snapshot: HourlyImportSnapshot, now: datetime) -> float:
    """Project total import for the hour at the current power rate."""
    hour_end = snapshot.hour_start + timedelta(hours=1)
    remaining_seconds = max(0.0, (hour_end - now).total_seconds())
    remaining_hours = remaining_seconds / 3600
    if snapshot.current_power_w is None or remaining_hours <= 0:
        return snapshot.consumed_kwh
    return snapshot.consumed_kwh + (snapshot.current_power_w / 1000) * remaining_hours
