"""Pure decision engine for Energy Dispatcher."""

from __future__ import annotations

from datetime import datetime, timedelta

from .const import (
    ENERGY_MODE_BLOCKED,
    ENERGY_MODE_GRID_CHEAP,
    ENERGY_MODE_GRID_EXPENSIVE,
    ENERGY_MODE_GRID_FREE,
    ENERGY_MODE_GRID_NORMAL,
    ENERGY_MODE_SOLAR,
    GRID_STATE_CRITICAL,
    PRICE_STATE_UNKNOWN,
    REASON_DATA_UNAVAILABLE,
    REASON_GRID_CHEAP,
    REASON_GRID_EXPENSIVE,
    REASON_GRID_EXPORT,
    REASON_GRID_FREE,
    REASON_GRID_NORMAL,
    REASON_NO_SOURCE,
    REASON_NOT_ALLOWED,
    REASON_NOT_CHEAP_YET,
    REASON_OVERRIDE,
    REASON_POWER_GUARD,
    STATE_OFF,
    STATE_ON,
    STATE_UNKNOWN,
)
from .decision_helpers import (
    available_export_power,
    classify_price,
    is_already_on,
    is_mode_allowed,
    is_price_data_ready,
    needs_price_data,
    price_state,
    solar_can_decide_without_price,
    solar_surplus_covers_load,
)
from .models import Decision, GlobalState, LoadConfig, OverrideState
from .runtime_scheduler import RuntimeTracker
from .price_timeline import current_slot
from .runtime_scheduler import evaluate_runtime_requirement


def evaluate_load(
    global_state: GlobalState,
    load: LoadConfig,
    runtime: RuntimeTracker,
    override: OverrideState | None = None,
    previous: Decision | None = None,
) -> Decision:
    """Evaluate whether a load should run and with which energy source."""
    grid_state = global_state.power_guard.state
    current = current_slot(global_state.price_timeline, global_state.now)
    price_state_value = price_state(current, global_state)

    base_kwargs = {
        "available_power": available_export_power(global_state),
        "required_power": load.required_power,
        "price_state": price_state_value,
        "grid_state": grid_state,
    }

    if grid_state == GRID_STATE_CRITICAL:
        return Decision(
            state=STATE_OFF,
            energy_mode=ENERGY_MODE_BLOCKED,
            reason=REASON_POWER_GUARD,
            reason_text=global_state.power_guard.reason_text or "Grid import power at critical level",
            next_opportunity=None,
            **base_kwargs,
        )

    if override is not None and override.expires_at > global_state.now:
        return Decision(
            state=STATE_ON if override.mode == "force_on" else STATE_OFF,
            energy_mode=ENERGY_MODE_BLOCKED,
            reason=REASON_OVERRIDE,
            reason_text="Manual override active",
            next_opportunity=None,
            **base_kwargs,
        )

    if (
        needs_price_data(load, global_state)
        and not is_price_data_ready(global_state)
        and not solar_can_decide_without_price(load, global_state, previous)
    ):
        return _unknown_decision(load, global_state, base_kwargs)

    export_decision = _evaluate_export(global_state, load, base_kwargs, previous)
    if export_decision is not None:
        return export_decision

    grid_decision = _evaluate_grid_now(global_state, load, base_kwargs)
    if grid_decision is not None:
        return grid_decision

    runtime_decision = evaluate_runtime_requirement(
        global_state, load, runtime, base_kwargs
    )
    if runtime_decision is not None:
        return runtime_decision

    next_opportunity, next_mode = _find_next_grid_opportunity(global_state, load)
    if next_opportunity is not None and next_mode is not None:
        return Decision(
            state=STATE_OFF,
            energy_mode=next_mode,
            reason=_reason_for_mode(next_mode, waiting=True),
            reason_text=_reason_text_for_mode(next_mode, waiting=True),
            next_opportunity=next_opportunity,
            **base_kwargs,
        )

    return Decision(
        state=STATE_OFF,
        energy_mode=ENERGY_MODE_BLOCKED,
        reason=REASON_NO_SOURCE,
        reason_text="No allowed energy source available",
        next_opportunity=None,
        **base_kwargs,
    )


def _unknown_decision(
    load: LoadConfig,
    global_state: GlobalState,
    base_kwargs: dict,
) -> Decision:
    return Decision(
        state=STATE_UNKNOWN,
        energy_mode=ENERGY_MODE_BLOCKED,
        reason=REASON_DATA_UNAVAILABLE,
        reason_text="Waiting for price sensor data",
        next_opportunity=None,
        available_power=base_kwargs["available_power"],
        required_power=load.required_power,
        price_state=PRICE_STATE_UNKNOWN,
        grid_state=base_kwargs["grid_state"],
    )


def _evaluate_export(
    global_state: GlobalState,
    load: LoadConfig,
    base_kwargs: dict,
    previous: Decision | None = None,
) -> Decision | None:
    sources = load.sources
    if not sources.solar_enabled:
        return None

    # Turn ON requires surplus covering the load. Once already ON, measured
    # export is residual after the load — keep/switch to SOLAR while exporting.
    if not solar_surplus_covers_load(load, global_state, previous):
        return None

    max_export = sources.solar_max_export_price
    if max_export is not None and global_state.export_price is not None:
        if global_state.export_price >= max_export:
            return None

    already_on = is_already_on(previous)
    return Decision(
        state=STATE_ON,
        energy_mode=ENERGY_MODE_SOLAR,
        reason=REASON_GRID_EXPORT,
        reason_text=(
            "Grid export continues — keep self-consumption"
            if already_on
            else "Grid export available — prefer self-consumption"
        ),
        next_opportunity=None,
        **base_kwargs,
    )


def _evaluate_grid_now(
    global_state: GlobalState,
    load: LoadConfig,
    base_kwargs: dict,
) -> Decision | None:
    current = current_slot(global_state.price_timeline, global_state.now)
    if current is None:
        return None

    mode = classify_price(current.price, global_state)
    if not is_mode_allowed(mode, load.sources):
        if mode == ENERGY_MODE_GRID_EXPENSIVE:
            return Decision(
                state=STATE_OFF,
                energy_mode=mode,
                reason=REASON_NOT_ALLOWED,
                reason_text="Expensive grid not allowed for this load",
                next_opportunity=None,
                **base_kwargs,
            )
        return None

    return Decision(
        state=STATE_ON,
        energy_mode=mode,
        reason=_reason_for_mode(mode),
        reason_text=_reason_text_for_mode(mode),
        next_opportunity=None,
        **base_kwargs,
    )


def _find_next_grid_opportunity(
    global_state: GlobalState,
    load: LoadConfig,
) -> tuple[datetime | None, str | None]:
    now = global_state.now
    hour_start = now.replace(minute=0, second=0, microsecond=0)
    if now.minute > 0 or now.second > 0 or now.microsecond > 0:
        hour_start += timedelta(hours=1)

    for slot in global_state.price_timeline:
        if slot.start < hour_start:
            continue
        mode = classify_price(slot.price, global_state)
        if is_mode_allowed(mode, load.sources):
            return slot.start, mode

    return None, None


def _reason_for_mode(mode: str, waiting: bool = False) -> str:
    if waiting and mode == ENERGY_MODE_GRID_CHEAP:
        return REASON_NOT_CHEAP_YET
    return {
        ENERGY_MODE_GRID_FREE: REASON_GRID_FREE,
        ENERGY_MODE_GRID_CHEAP: REASON_GRID_CHEAP,
        ENERGY_MODE_GRID_NORMAL: REASON_GRID_NORMAL,
        ENERGY_MODE_GRID_EXPENSIVE: REASON_GRID_EXPENSIVE,
    }.get(mode, REASON_NO_SOURCE)


def _reason_text_for_mode(mode: str, waiting: bool = False) -> str:
    if waiting:
        return {
            ENERGY_MODE_GRID_FREE: "Waiting for free grid window",
            ENERGY_MODE_GRID_CHEAP: "Waiting for cheap grid window",
            ENERGY_MODE_GRID_NORMAL: "Waiting for normal grid window",
            ENERGY_MODE_GRID_EXPENSIVE: "Waiting for allowed grid window",
        }.get(mode, "Waiting for allowed energy source")
    return {
        ENERGY_MODE_GRID_FREE: "Grid price at or below free threshold",
        ENERGY_MODE_GRID_CHEAP: "Grid price below cheap threshold",
        ENERGY_MODE_GRID_NORMAL: "Grid price within normal range",
        ENERGY_MODE_GRID_EXPENSIVE: "Grid price above expensive threshold",
    }.get(mode, "Allowed grid source available")
