"""Learn load power peaks from a power sensor (HA-free core)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

IDLE_POWER_W = 20.0
BLOCK_MINUTES = 5
RETENTION_DAYS = 7


@dataclass
class PowerPeak:
    """A recorded block-average peak while the load was ON."""

    at: datetime
    watts: float

    def to_dict(self) -> dict:
        return {"at": self.at.isoformat(), "watts": self.watts}

    @classmethod
    def from_dict(cls, data: dict) -> PowerPeak:
        return cls(at=datetime.fromisoformat(data["at"]), watts=float(data["watts"]))


@dataclass
class _ActiveBlock:
    start: datetime
    samples: list[float] = field(default_factory=list)


@dataclass
class LoadPowerLearner:
    """Tracks 5-minute block averages while ON and keeps a 7-day peak history."""

    peaks: list[PowerPeak] = field(default_factory=list)
    _active: _ActiveBlock | None = None

    def learned_required_power(self, now: datetime) -> float | None:
        self.prune(now)
        if not self.peaks:
            return None
        return max(peak.watts for peak in self.peaks)

    def prune(self, now: datetime) -> None:
        cutoff = now - timedelta(days=RETENTION_DAYS)
        self.peaks = [peak for peak in self.peaks if peak.at >= cutoff]

    def sample(self, now: datetime, watts: float | None, *, is_on: bool) -> bool:
        """Update learning. Returns True if persisted peak history changed."""
        changed = False
        self.prune(now)

        if not is_on or watts is None:
            changed = self._finalize_block(now) or changed
            return changed

        if self._active is None:
            self._active = _ActiveBlock(start=now, samples=[watts])
            return changed

        self._active.samples.append(watts)
        elapsed = (now - self._active.start).total_seconds() / 60.0
        if elapsed >= BLOCK_MINUTES:
            changed = self._finalize_block(now) or changed
            self._active = _ActiveBlock(start=now, samples=[watts])
        return changed

    def _finalize_block(self, now: datetime) -> bool:
        if self._active is None or not self._active.samples:
            self._active = None
            return False
        avg = sum(self._active.samples) / len(self._active.samples)
        self._active = None
        if avg < IDLE_POWER_W:
            return False
        self.peaks.append(PowerPeak(at=now, watts=avg))
        self.prune(now)
        return True

    def to_dict(self) -> dict:
        return {"peaks": [peak.to_dict() for peak in self.peaks]}

    @classmethod
    def from_dict(cls, data: dict | None) -> LoadPowerLearner:
        if not data:
            return cls()
        peaks = [PowerPeak.from_dict(item) for item in data.get("peaks", [])]
        return cls(peaks=peaks)
