"""Services for Energy Dispatcher."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN,
    SERVICE_CLEAR_OVERRIDE,
    SERVICE_OVERRIDE,
    SERVICE_RECALCULATE,
)
from .entity import EnergyDispatcherEntity

_LOGGER = logging.getLogger(__name__)

SERVICE_OVERRIDE_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_ids,
        vol.Required("mode"): vol.In(["force_on", "force_off"]),
        vol.Required("duration"): cv.time_period,
    }
)

SERVICE_ENTITY_SCHEMA = vol.Schema({vol.Required("entity_id"): cv.entity_ids})


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register Energy Dispatcher services."""

    async def handle_override(call: ServiceCall) -> None:
        duration = call.data["duration"]
        mode = call.data["mode"]
        for entity_id in call.data["entity_id"]:
            entity = _get_entity(hass, entity_id)
            if entity is None:
                continue
            entity.coordinator.set_override(entity.load_id, mode, duration)
            await entity.coordinator.async_request_refresh()
            _log_decision(entity, "override applied")

    async def handle_clear_override(call: ServiceCall) -> None:
        for entity_id in call.data["entity_id"]:
            entity = _get_entity(hass, entity_id)
            if entity is None:
                continue
            entity.coordinator.clear_override(entity.load_id)
            await entity.coordinator.async_request_refresh()

    async def handle_recalculate(call: ServiceCall) -> None:
        coordinators = set()
        for entity_id in call.data["entity_id"]:
            entity = _get_entity(hass, entity_id)
            if entity is None:
                continue
            coordinators.add(entity.coordinator)
        for coordinator in coordinators:
            await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_OVERRIDE,
        handle_override,
        schema=SERVICE_OVERRIDE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAR_OVERRIDE,
        handle_clear_override,
        schema=SERVICE_ENTITY_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_RECALCULATE,
        handle_recalculate,
        schema=SERVICE_ENTITY_SCHEMA,
    )


def _get_entity(hass: HomeAssistant, entity_id: str) -> EnergyDispatcherEntity | None:
    for entry_data in hass.data.get(DOMAIN, {}).values():
        if not isinstance(entry_data, dict):
            continue
        for entity in entry_data.get("entities", []):
            if entity.entity_id == entity_id:
                return entity
    return None


def _log_decision(entity: EnergyDispatcherEntity, message: str) -> None:
    decision = entity.decision
    if decision is None:
        _LOGGER.info("%s: %s", entity.entity_id, message)
        return
    _LOGGER.info(
        "%s: %s (mode=%s, reason=%s)",
        entity.entity_id,
        decision.state,
        decision.energy_mode,
        decision.reason,
    )
