"""Power guard models and strategy evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .const import (
    GRID_STATE_CRITICAL,
    GRID_STATE_NORMAL,
    GRID_STATE_WARNING,
    POWER_GUARD_STRATEGY_NONE,
    POWER_GUARD_STRATEGY_SIMPLE_THRESHOLD,
    REASON_POWER_GUARD,
)
from .hourly_aggregator import HourlyImportSnapshot, projected_hour_kwh


@dataclass(frozen=True)
class PowerGuardConfig:
    """Configuration for the active power guard strategy."""

    strategy: str
    hourly_limit_kwh: float | None = None


@dataclass(frozen=True)
class PowerGuardState:
    """Normalized power guard result consumed by the decision engine."""

    state: str
    strategy: str
    current_peak_average: float | None = None
    headroom: float | None = None
    current_import_power: float | None = None
    current_hour_kwh: float | None = None
    projected_hour_kwh: float | None = None
    hourly_limit_kwh: float | None = None
    billing_period: str | None = None
    reason: str = ""
    reason_text: str = ""


def evaluate_power_guard(
    config: PowerGuardConfig,
    hourly: HourlyImportSnapshot,
    now: datetime,
) -> PowerGuardState:
    """Evaluate power guard using the configured strategy."""
    if config.strategy == POWER_GUARD_STRATEGY_NONE:
        return PowerGuardState(
            state=GRID_STATE_NORMAL,
            strategy=config.strategy,
            reason_text="Power guard disabled",
        )

    if config.strategy == POWER_GUARD_STRATEGY_SIMPLE_THRESHOLD:
        return _evaluate_simple_threshold(config, hourly, now)

    return PowerGuardState(
        state=GRID_STATE_NORMAL,
        strategy=config.strategy,
        reason_text=f"Unsupported power guard strategy: {config.strategy}",
    )


def _evaluate_simple_threshold(
    config: PowerGuardConfig,
    hourly: HourlyImportSnapshot,
    now: datetime,
) -> PowerGuardState:
    """Hourly import limit: CRITICAL if consumed, WARNING if projected to exceed."""
    limit = config.hourly_limit_kwh
    if limit is None:
        return PowerGuardState(
            state=GRID_STATE_NORMAL,
            strategy=config.strategy,
            reason_text="Hourly import limit not configured",
        )

    if hourly.current_power_w is None:
        return PowerGuardState(
            state=GRID_STATE_NORMAL,
            strategy=config.strategy,
            current_hour_kwh=hourly.consumed_kwh,
            hourly_limit_kwh=limit,
            reason_text="Grid input sensor unavailable",
        )

    consumed = hourly.consumed_kwh
    projected = projected_hour_kwh(hourly, now)
    base = {
        "strategy": config.strategy,
        "current_import_power": hourly.current_power_w,
        "current_hour_kwh": consumed,
        "projected_hour_kwh": projected,
        "hourly_limit_kwh": limit,
    }

    if consumed >= limit:
        return PowerGuardState(
            state=GRID_STATE_CRITICAL,
            reason=REASON_POWER_GUARD,
            reason_text=f"Hourly import limit reached ({consumed:.2f}/{limit:.2f} kWh)",
            headroom=0.0,
            **base,
        )

    if projected > limit:
        return PowerGuardState(
            state=GRID_STATE_WARNING,
            reason=REASON_POWER_GUARD,
            reason_text=(
                f"Current import rate projects above hourly limit "
                f"({projected:.2f}/{limit:.2f} kWh)"
            ),
            headroom=max(0.0, limit - projected),
            **base,
        )

    return PowerGuardState(
        state=GRID_STATE_NORMAL,
        reason_text="Hourly import within limit",
        headroom=max(0.0, limit - projected),
        **base,
    )
