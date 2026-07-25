"""Shared decision helpers without circular imports."""

from __future__ import annotations

from .const import (
    ENERGY_MODE_GRID_CHEAP,
    ENERGY_MODE_GRID_EXPENSIVE,
    ENERGY_MODE_GRID_FREE,
    ENERGY_MODE_GRID_NORMAL,
    ENERGY_MODE_SOLAR,
    PRICE_STATE_HIGH,
    PRICE_STATE_LOW,
    PRICE_STATE_NORMAL,
    PRICE_STATE_UNKNOWN,
    STATE_ON,
)
from .models import Decision, GlobalState, LoadConfig, LoadPowerSnapshot, PriceSlot, SourceRules
from .price_timeline import current_slot


def available_export_power(global_state: GlobalState) -> float:
    if global_state.grid_output is None or global_state.grid_output <= 0:
        return 0.0
    return global_state.grid_output


def classify_price(price: float, global_state: GlobalState) -> str:
    thresholds = global_state.price_thresholds
    if price <= thresholds.free_threshold:
        return ENERGY_MODE_GRID_FREE

    average = global_state.rolling_average_price
    if average is not None and average > 0:
        ratio = price / average
        if ratio < thresholds.cheap_ratio:
            return ENERGY_MODE_GRID_CHEAP
        if ratio > thresholds.expensive_ratio:
            return ENERGY_MODE_GRID_EXPENSIVE
        return ENERGY_MODE_GRID_NORMAL

    return ENERGY_MODE_GRID_NORMAL


def is_mode_allowed(mode: str, sources: SourceRules) -> bool:
    mapping = {
        ENERGY_MODE_GRID_FREE: sources.grid_free_enabled,
        ENERGY_MODE_GRID_CHEAP: sources.grid_cheap_enabled,
        ENERGY_MODE_GRID_NORMAL: sources.grid_normal_enabled,
        ENERGY_MODE_GRID_EXPENSIVE: sources.grid_expensive_enabled,
    }
    return mapping.get(mode, False)


def price_state(current: PriceSlot | None, global_state: GlobalState) -> str:
    if current is None:
        return PRICE_STATE_UNKNOWN
    mode = classify_price(current.price, global_state)
    if mode in (ENERGY_MODE_GRID_FREE, ENERGY_MODE_GRID_CHEAP, ENERGY_MODE_SOLAR):
        return PRICE_STATE_LOW
    if mode == ENERGY_MODE_GRID_EXPENSIVE:
        return PRICE_STATE_HIGH
    return PRICE_STATE_NORMAL


def has_grid_sources(sources: SourceRules) -> bool:
    return any(
        (
            sources.grid_free_enabled,
            sources.grid_cheap_enabled,
            sources.grid_normal_enabled,
            sources.grid_expensive_enabled,
        )
    )


def is_price_data_ready(global_state: GlobalState) -> bool:
    return current_slot(global_state.price_timeline, global_state.now) is not None


def needs_price_data(load: LoadConfig, global_state: GlobalState) -> bool:
    if load.minimum_minutes_per_day or load.minimum_minutes_per_week:
        return True
    if has_grid_sources(load.sources):
        return True
    if (
        load.sources.solar_enabled
        and load.sources.solar_max_export_price is not None
    ):
        return True
    return False


def is_already_on(previous: Decision | None) -> bool:
    """True when the previous decision already recommended ON."""
    return previous is not None and previous.state == STATE_ON


def is_already_solar_on(previous: Decision | None) -> bool:
    """True when the previous decision already recommended ON / SOLAR."""
    return is_already_on(previous) and previous.energy_mode == ENERGY_MODE_SOLAR


def solar_surplus_covers_load(
    global_state: GlobalState,
    power: LoadPowerSnapshot,
) -> bool:
    """Whether SOLAR self-consumption is available for full rated power.

    Requires ongoing export. Headroom for full rated power is estimated as
    ``export + measured_power`` (residual export plus what the load already
    draws — i.e. surplus if the load were off / at full draw).

    Example: export 100 W, measured 10 W, required 1000 W → 110 < 1000 → no.
    Example: export 100 W, measured 1000 W, required 1000 W → 1100 >= 1000 → yes.

    Cold start (required unknown): chance SOLAR while any export remains.
    """
    export_power = available_export_power(global_state)
    if export_power <= 0:
        return False
    required = power.effective_required_power
    if required is None:
        return True
    return export_power + max(0.0, power.measured_power) >= required


def solar_conditions_met(
    global_state: GlobalState,
    load: LoadConfig,
    power: LoadPowerSnapshot,
) -> bool:
    """True when surplus/export-price rules would allow SOLAR right now."""
    if not load.sources.solar_enabled:
        return False
    if not solar_surplus_covers_load(global_state, power):
        return False
    max_export = load.sources.solar_max_export_price
    if max_export is not None and global_state.export_price is not None:
        if global_state.export_price >= max_export:
            return False
    return True


def update_solar_eligibility(
    *,
    conditions_met: bool,
    now: datetime,
    eligible_since: datetime | None,
    sustain_minutes: float,
) -> tuple[datetime | None, bool, float]:
    """Track sustained SOLAR eligibility.

    Returns (new_eligible_since, entry_ready, remaining_seconds).
    Entry requires conditions_met continuously for sustain_minutes.
    """
    if not conditions_met:
        return None, False, 0.0
    since = eligible_since or now
    elapsed = (now - since).total_seconds()
    needed = sustain_minutes * 60.0
    remaining = max(0.0, needed - elapsed)
    return since, remaining <= 0, remaining


def solar_can_decide_without_price(
    load: LoadConfig,
    global_state: GlobalState,
    power: LoadPowerSnapshot,
) -> bool:
    if not load.sources.solar_enabled:
        return False
    if not solar_surplus_covers_load(global_state, power):
        return False
    if (
        load.sources.solar_max_export_price is not None
        and global_state.export_price is None
    ):
        return False
    return True
