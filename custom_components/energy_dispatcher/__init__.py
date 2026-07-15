"""The Energy Dispatcher integration."""

from __future__ import annotations

from types import MappingProxyType
import logging
from typing import TYPE_CHECKING

from .const import CONF_LOADS, DOMAIN, PLATFORMS, SUBENTRY_TYPE_LOAD
from .models import load_config_from_dict, load_config_to_subentry_data

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up services once for the integration."""
    from .services import async_setup_services

    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Energy Dispatcher from a config entry."""
    from homeassistant.helpers import device_registry as dr

    from .coordinator import EnergyDispatcherCoordinator

    _LOGGER.debug("Setting up config entry %s", entry.entry_id)
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        manufacturer="Energy Dispatcher",
        model="Hub",
        name=entry.title,
    )

    coordinator = EnergyDispatcherCoordinator(hass, entry)
    await coordinator.async_load_runtime()
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "entities": [],
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.debug(
        "Setup complete for %s with %d loads",
        entry.entry_id,
        len(coordinator.loads),
    )

    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate config entry structure."""
    from homeassistant.config_entries import ConfigSubentry

    if entry.version == 1:
        for load_data in entry.options.get(CONF_LOADS, []):
            load = load_config_from_dict(load_data)
            hass.config_entries.async_add_subentry(
                entry,
                ConfigSubentry(
                    data=MappingProxyType(load_config_to_subentry_data(load)),
                    subentry_type=SUBENTRY_TYPE_LOAD,
                    title=load.name,
                    unique_id=load.load_id,
                ),
            )
        hass.config_entries.async_update_entry(entry, version=2, options={})
    return True


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
