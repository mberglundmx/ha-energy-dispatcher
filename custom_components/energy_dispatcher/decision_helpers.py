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
)
from .models import GlobalState, PriceSlot, SourceRules


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
        return PRICE_STATE_NORMAL
    mode = classify_price(current.price, global_state)
    if mode in (ENERGY_MODE_GRID_FREE, ENERGY_MODE_GRID_CHEAP, ENERGY_MODE_SOLAR):
        return PRICE_STATE_LOW
    if mode == ENERGY_MODE_GRID_EXPENSIVE:
        return PRICE_STATE_HIGH
    return PRICE_STATE_NORMAL
