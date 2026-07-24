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
from .models import Decision, GlobalState, PriceSlot, SourceRules, LoadConfig
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
    load: LoadConfig,
    global_state: GlobalState,
    previous: Decision | None = None,
) -> bool:
    """Whether SOLAR self-consumption is available.

    Turn ON requires export ≥ required_power. Once the load is already ON,
    measured export is residual after the load — keep/switch to SOLAR while
    any export remains.
    """
    export_power = available_export_power(global_state)
    if is_already_on(previous):
        return export_power > 0
    return export_power >= load.required_power


def solar_can_decide_without_price(
    load: LoadConfig,
    global_state: GlobalState,
    previous: Decision | None = None,
) -> bool:
    if not load.sources.solar_enabled:
        return False
    if not solar_surplus_covers_load(load, global_state, previous):
        return False
    if (
        load.sources.solar_max_export_price is not None
        and global_state.export_price is None
    ):
        return False
    return True
