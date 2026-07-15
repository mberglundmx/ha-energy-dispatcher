"""DataUpdateCoordinator for Energy Dispatcher."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_EXPORT_PRICE_OFFSET,
    CONF_GRID_IMPORT_POWER_SENSOR,
    CONF_GRID_INPUT_SENSOR,
    CONF_GRID_OUTPUT_SENSOR,
    CONF_GRID_POWER_SENSOR,
    CONF_LOADS,
    CONF_POWER_GUARD_HOURLY_LIMIT_KWH,
    CONF_POWER_GUARD_STRATEGY,
    CONF_PRICE_CHEAP_RATIO,
    CONF_PRICE_EXPENSIVE_RATIO,
    CONF_PRICE_FREE_THRESHOLD,
    CONF_PRICE_SENSOR,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    POWER_GUARD_STRATEGY_NONE,
    POWER_GUARD_STRATEGY_SIMPLE_THRESHOLD,
    STATE_ON,
)
from .decision_engine import evaluate_load
from .hourly_aggregator import HourlyAggregator
from .models import (
    GlobalState,
    LoadConfig,
    LoadRuntimeState,
    OverrideState,
    PriceThresholds,
    load_config_from_dict,
)
from .power_guard import PowerGuardConfig, evaluate_power_guard
from .price_provider import PriceProvider
from .price_timeline import compute_rolling_average, current_slot
from .runtime_scheduler import RuntimeTracker, accumulate_runtime

_LOGGER = logging.getLogger(__name__)
STORAGE_VERSION = 1
STORAGE_KEY = "energy_dispatcher.runtime"


class EnergyDispatcherCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that maintains global sensor state and load decisions."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.entry = entry
        self.loads: dict[str, LoadConfig] = {}
        self.runtime: dict[str, LoadRuntimeState] = {}
        self._runtime_trackers: dict[str, RuntimeTracker] = {}
        self._hourly_aggregator = HourlyAggregator()
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._reload_loads()

    async def async_load_runtime(self) -> None:
        data = await self._store.async_load() or {}
        for load_id, tracker_data in data.items():
            self._runtime_trackers[load_id] = RuntimeTracker.from_dict(tracker_data)

    async def _async_update_data(self) -> dict[str, Any]:
        now = dt_util.now()
        data = self._build_global_state(now)
        interval_minutes = DEFAULT_SCAN_INTERVAL / 60
        runtime_dirty = False
        decisions = {}

        for load_id, load in self.loads.items():
            runtime = self.runtime.setdefault(load_id, LoadRuntimeState())
            runtime.override = _clear_expired_override(runtime.override, now)
            tracker = self._runtime_trackers.setdefault(load_id, RuntimeTracker())
            decision = evaluate_load(data, load, tracker, runtime.override)
            previous = runtime.last_decision

            if previous is not None and previous.state == STATE_ON:
                updated = accumulate_runtime(
                    tracker, now, interval_minutes, was_on=True
                )
                if updated.to_dict() != tracker.to_dict():
                    self._runtime_trackers[load_id] = updated
                    runtime_dirty = True

            if _decision_changed(previous, decision):
                _LOGGER.info(
                    "%s: %s → %s (mode=%s, reason=%s)",
                    load.name,
                    previous.state if previous else None,
                    decision.state,
                    decision.energy_mode,
                    decision.reason,
                )
            runtime.last_decision = decision
            decisions[load_id] = decision

        if runtime_dirty:
            await self._store.async_save(
                {
                    load_id: tracker.to_dict()
                    for load_id, tracker in self._runtime_trackers.items()
                }
            )

        return {"global_state": data, "decisions": decisions}

    def _reload_loads(self) -> None:
        loads_data = self.entry.options.get(CONF_LOADS, [])
        self.loads = {}
        for item in loads_data:
            load = load_config_from_dict(item)
            self.loads[load.load_id] = load
            if load.load_id not in self.runtime:
                self.runtime[load.load_id] = LoadRuntimeState()

    def _build_global_state(self, now: datetime) -> GlobalState:
        price_sensor = self.entry.data[CONF_PRICE_SENSOR]
        price_provider = PriceProvider(self.hass, price_sensor)
        timeline = price_provider.get_timeline(now)

        grid_input = _read_grid_power(self.hass, self.entry.data, input_sensor=True)
        grid_output = _read_grid_power(self.hass, self.entry.data, input_sensor=False)
        export_price = _read_export_price(self.hass, self.entry.data, timeline, now)
        hourly = self._hourly_aggregator.update(grid_input, now)
        power_guard = evaluate_power_guard(
            _power_guard_config(self.entry.data),
            hourly,
            now,
        )

        return GlobalState(
            now=now,
            grid_input=grid_input,
            grid_output=grid_output,
            export_price=export_price,
            price_timeline=timeline,
            rolling_average_price=compute_rolling_average(timeline, now),
            power_guard=power_guard,
            price_thresholds=PriceThresholds(
                free_threshold=float(
                    self.entry.data.get(CONF_PRICE_FREE_THRESHOLD, 0.02)
                ),
                cheap_ratio=float(self.entry.data.get(CONF_PRICE_CHEAP_RATIO, 0.3)),
                expensive_ratio=float(
                    self.entry.data.get(CONF_PRICE_EXPENSIVE_RATIO, 1.5)
                ),
            ),
        )

    def get_runtime_tracker(self, load_id: str) -> RuntimeTracker:
        return self._runtime_trackers.get(load_id, RuntimeTracker())

    def set_override(
        self, load_id: str, mode: str, duration: timedelta
    ) -> None:
        runtime = self.runtime.setdefault(load_id, LoadRuntimeState())
        runtime.override = OverrideState(
            mode=mode,
            expires_at=dt_util.now() + duration,
        )

    def clear_override(self, load_id: str) -> None:
        runtime = self.runtime.setdefault(load_id, LoadRuntimeState())
        runtime.override = None


def _grid_input_entity(config: dict[str, Any]) -> str | None:
    return (
        config.get(CONF_GRID_INPUT_SENSOR)
        or config.get(CONF_GRID_IMPORT_POWER_SENSOR)
        or config.get(CONF_GRID_POWER_SENSOR)
    )


def _grid_output_entity(config: dict[str, Any]) -> str | None:
    return config.get(CONF_GRID_OUTPUT_SENSOR)


def _read_grid_power(
    hass: HomeAssistant, config: dict[str, Any], *, input_sensor: bool
) -> float | None:
    entity_id = _grid_input_entity(config) if input_sensor else _grid_output_entity(config)
    if not entity_id:
        return None
    state = hass.states.get(entity_id)
    if state is None or state.state in ("unknown", "unavailable", None, ""):
        return None
    try:
        return max(0.0, float(state.state))
    except (TypeError, ValueError):
        return None


def _power_guard_config(data: dict[str, Any]) -> PowerGuardConfig:
    strategy = data.get(CONF_POWER_GUARD_STRATEGY, POWER_GUARD_STRATEGY_NONE)
    if strategy == POWER_GUARD_STRATEGY_SIMPLE_THRESHOLD and not _grid_input_entity(data):
        strategy = POWER_GUARD_STRATEGY_NONE
    return PowerGuardConfig(
        strategy=strategy,
        hourly_limit_kwh=_optional_float(data.get(CONF_POWER_GUARD_HOURLY_LIMIT_KWH)),
    )


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _read_export_price(
    hass: HomeAssistant,
    config: dict[str, Any],
    timeline: tuple,
    now: datetime,
) -> float | None:
    """Estimate export price as spot price plus fixed compensation."""
    offset = config.get(CONF_EXPORT_PRICE_OFFSET)
    if offset is None:
        return None

    current = current_slot(timeline, now)
    if current is None:
        return None
    return current.price + float(offset)


def _clear_expired_override(
    override: OverrideState | None, now: datetime
) -> OverrideState | None:
    if override is None:
        return None
    if override.expires_at <= now:
        return None
    return override


def _decision_changed(previous, current) -> bool:
    if previous is None:
        return True
    return (
        previous.state != current.state
        or previous.energy_mode != current.energy_mode
        or previous.reason != current.reason
    )
