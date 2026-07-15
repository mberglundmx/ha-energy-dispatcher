"""Platform for Energy Dispatcher entities."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import EnergyDispatcherCoordinator
from .entity import EnergyDispatcherEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Energy Dispatcher entities from a config entry."""
    coordinator: EnergyDispatcherCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        EnergyDispatcherEntity(coordinator, load)
        for load in coordinator.loads.values()
    ]
    hass.data[DOMAIN][entry.entry_id]["entities"] = entities
    async_add_entities(entities)
