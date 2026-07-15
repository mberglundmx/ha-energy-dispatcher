"""Platform for Energy Dispatcher entities."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SUBENTRY_TYPE_LOAD
from .coordinator import EnergyDispatcherCoordinator
from .entity import EnergyDispatcherEntity
from .models import load_config_from_subentry

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Energy Dispatcher entities from a config entry."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    coordinator: EnergyDispatcherCoordinator = entry_data["coordinator"]

    entities = []
    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_TYPE_LOAD:
            continue
        load = load_config_from_subentry(subentry)
        entities.append(
            EnergyDispatcherEntity(coordinator, load, subentry.subentry_id)
        )

    hass.data[DOMAIN][entry.entry_id]["entities"] = entities
    _LOGGER.debug("Added %d entities for entry %s", len(entities), entry.entry_id)
    async_add_entities(entities)
