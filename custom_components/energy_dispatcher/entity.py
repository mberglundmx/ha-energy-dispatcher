"""Energy Dispatcher entity."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_AVAILABLE_POWER,
    ATTR_ENERGY_MODE,
    ATTR_GRID_STATE,
    ATTR_NEXT_OPPORTUNITY,
    ATTR_POWER_GUARD_BILLING_PERIOD,
    ATTR_POWER_GUARD_HEADROOM,
    ATTR_POWER_GUARD_HOUR_KWH,
    ATTR_POWER_GUARD_HOURLY_LIMIT_KWH,
    ATTR_POWER_GUARD_IMPORT_POWER,
    ATTR_POWER_GUARD_PEAK_AVERAGE,
    ATTR_POWER_GUARD_PROJECTED_HOUR_KWH,
    ATTR_POWER_GUARD_STRATEGY,
    ATTR_PRICE_STATE,
    ATTR_REASON,
    ATTR_REASON_TEXT,
    ATTR_REQUIRED_POWER,
    ATTR_RUNTIME_MINUTES_TODAY,
    ATTR_RUNTIME_MINUTES_WEEK,
    ATTR_RUNTIME_REMAINING_MINUTES,
    DOMAIN,
    POWER_GUARD_STRATEGY_NONE,
)
from .coordinator import EnergyDispatcherCoordinator
from .runtime_scheduler import remaining_runtime_minutes
from .models import Decision, LoadConfig


class EnergyDispatcherEntity(CoordinatorEntity[EnergyDispatcherCoordinator], Entity):
    """Representation of a dispatch target."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EnergyDispatcherCoordinator,
        load: LoadConfig,
        subentry_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._load = load
        self._subentry_id = subentry_id
        self._config_subentry_id = subentry_id
        self._attr_unique_id = subentry_id
        self._attr_name = load.name

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._subentry_id)},
            name=self._load.name,
            manufacturer="Energy Dispatcher",
            via_device={(DOMAIN, self.coordinator.entry.entry_id)},
        )

    @property
    def decision(self) -> Decision | None:
        data = self.coordinator.data
        if not data:
            return None
        return data.get("decisions", {}).get(self._load.load_id)

    @property
    def suggested_object_id(self) -> str:
        return self._load.load_id

    @property
    def state(self) -> str | None:
        decision = self.decision
        return decision.state if decision else None

    @property
    def extra_state_attributes(self) -> dict:
        decision = self.decision
        if decision is None:
            return {}

        attrs = {
            ATTR_ENERGY_MODE: decision.energy_mode,
            ATTR_REASON: decision.reason,
            ATTR_REASON_TEXT: decision.reason_text,
            ATTR_AVAILABLE_POWER: decision.available_power,
            ATTR_REQUIRED_POWER: decision.required_power,
            ATTR_PRICE_STATE: decision.price_state,
            ATTR_GRID_STATE: decision.grid_state,
        }
        if decision.next_opportunity is not None:
            attrs[ATTR_NEXT_OPPORTUNITY] = decision.next_opportunity.isoformat()

        tracker = self.coordinator.get_runtime_tracker(self._load.load_id)
        remaining = remaining_runtime_minutes(self._load, tracker)
        if (
            self._load.minimum_minutes_per_day is not None
            or self._load.minimum_minutes_per_week is not None
        ):
            attrs[ATTR_RUNTIME_MINUTES_TODAY] = tracker.minutes_today
            attrs[ATTR_RUNTIME_MINUTES_WEEK] = tracker.minutes_week
            attrs[ATTR_RUNTIME_REMAINING_MINUTES] = remaining

        power_guard = self._power_guard_state()
        if power_guard is not None and power_guard.strategy != POWER_GUARD_STRATEGY_NONE:
            attrs[ATTR_POWER_GUARD_STRATEGY] = power_guard.strategy
            if power_guard.current_peak_average is not None:
                attrs[ATTR_POWER_GUARD_PEAK_AVERAGE] = power_guard.current_peak_average
            if power_guard.headroom is not None:
                attrs[ATTR_POWER_GUARD_HEADROOM] = power_guard.headroom
            if power_guard.billing_period is not None:
                attrs[ATTR_POWER_GUARD_BILLING_PERIOD] = power_guard.billing_period
            if power_guard.current_import_power is not None:
                attrs[ATTR_POWER_GUARD_IMPORT_POWER] = power_guard.current_import_power
            if power_guard.current_hour_kwh is not None:
                attrs[ATTR_POWER_GUARD_HOUR_KWH] = power_guard.current_hour_kwh
            if power_guard.projected_hour_kwh is not None:
                attrs[ATTR_POWER_GUARD_PROJECTED_HOUR_KWH] = power_guard.projected_hour_kwh
            if power_guard.hourly_limit_kwh is not None:
                attrs[ATTR_POWER_GUARD_HOURLY_LIMIT_KWH] = power_guard.hourly_limit_kwh

        return attrs

    def _power_guard_state(self):
        data = self.coordinator.data
        if not data:
            return None
        global_state = data.get("global_state")
        if global_state is None:
            return None
        return global_state.power_guard

    @property
    def load_id(self) -> str:
        return self._load.load_id
