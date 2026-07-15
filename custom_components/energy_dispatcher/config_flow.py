"""Config flow for Energy Dispatcher."""

from __future__ import annotations

from typing import Any
import uuid

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_EXPORT_PRICE_OFFSET,
    CONF_EXPORT_PRICE_SENSOR,
    CONF_GRID_INPUT_SENSOR,
    CONF_GRID_OUTPUT_SENSOR,
    CONF_LOAD_ID,
    CONF_LOAD_NAME,
    CONF_LOADS,
    CONF_POWER_GUARD_HOURLY_LIMIT_KWH,
    CONF_POWER_GUARD_STRATEGY,
    CONF_PRICE_CHEAP_RATIO,
    CONF_PRICE_EXPENSIVE_RATIO,
    CONF_PRICE_FREE_THRESHOLD,
    CONF_PRICE_SENSOR,
    CONF_REQUIRED_POWER,
    DEFAULT_POWER_GUARD_HOURLY_LIMIT_KWH,
    DEFAULT_PRICE_CHEAP_RATIO,
    DEFAULT_PRICE_EXPENSIVE_RATIO,
    DEFAULT_PRICE_FREE_THRESHOLD,
    DOMAIN,
    POWER_GUARD_STRATEGY_NONE,
    POWER_GUARD_STRATEGY_SIMPLE_THRESHOLD,
)
from .models import LoadConfig, SourceRules, load_config_to_dict

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PRICE_SENSOR): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        ),
        vol.Required(CONF_GRID_INPUT_SENSOR): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        ),
        vol.Required(CONF_GRID_OUTPUT_SENSOR): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        ),
        vol.Optional(CONF_EXPORT_PRICE_SENSOR): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        ),
        vol.Optional(CONF_EXPORT_PRICE_OFFSET): vol.Coerce(float),
        vol.Optional(
            CONF_POWER_GUARD_STRATEGY, default=POWER_GUARD_STRATEGY_NONE
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    POWER_GUARD_STRATEGY_NONE,
                    POWER_GUARD_STRATEGY_SIMPLE_THRESHOLD,
                ],
                translation_key="power_guard_strategy",
            )
        ),
        vol.Optional(
            CONF_POWER_GUARD_HOURLY_LIMIT_KWH,
            default=DEFAULT_POWER_GUARD_HOURLY_LIMIT_KWH,
        ): vol.Coerce(float),
        vol.Optional(CONF_PRICE_FREE_THRESHOLD, default=DEFAULT_PRICE_FREE_THRESHOLD): vol.Coerce(
            float
        ),
        vol.Optional(CONF_PRICE_CHEAP_RATIO, default=DEFAULT_PRICE_CHEAP_RATIO): vol.Coerce(float),
        vol.Optional(
            CONF_PRICE_EXPENSIVE_RATIO, default=DEFAULT_PRICE_EXPENSIVE_RATIO
        ): vol.Coerce(float),
    }
)

LOAD_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_LOAD_NAME): str,
        vol.Required(CONF_REQUIRED_POWER): vol.Coerce(float),
        vol.Required("solar_enabled", default=True): bool,
        vol.Optional("solar_max_export_price"): vol.Coerce(float),
        vol.Optional("minimum_minutes_per_day"): vol.Coerce(int),
        vol.Optional("minimum_minutes_per_week"): vol.Coerce(int),
        vol.Required("grid_free_enabled", default=False): bool,
        vol.Required("grid_cheap_enabled", default=True): bool,
        vol.Required("grid_normal_enabled", default=False): bool,
        vol.Required("grid_expensive_enabled", default=False): bool,
    }
)


class EnergyDispatcherConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Energy Dispatcher."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()

            if not user_input.get(CONF_EXPORT_PRICE_SENSOR) and user_input.get(
                CONF_EXPORT_PRICE_OFFSET
            ) is None:
                errors["base"] = "export_price_required"
            else:
                return self.async_create_entry(title="Energy Dispatcher", data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )


class EnergyDispatcherOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for adding and removing loads."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            if user_input["action"] == "add":
                return await self.async_step_add_load()
            return await self.async_step_remove_load()

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({vol.Required("action"): vol.In(["add", "remove"])}),
        )

    async def async_step_add_load(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            load_id = _slugify(user_input[CONF_LOAD_NAME])
            if _load_id_exists(self.config_entry, load_id):
                return self.async_show_form(
                    step_id="add_load",
                    data_schema=LOAD_SCHEMA,
                    errors={"base": "load_exists"},
                )

            load = LoadConfig(
                load_id=load_id,
                name=user_input[CONF_LOAD_NAME],
                required_power=user_input[CONF_REQUIRED_POWER],
                minimum_minutes_per_day=user_input.get("minimum_minutes_per_day"),
                minimum_minutes_per_week=user_input.get("minimum_minutes_per_week"),
                sources=SourceRules(
                    solar_enabled=user_input["solar_enabled"],
                    solar_max_export_price=user_input.get("solar_max_export_price"),
                    grid_free_enabled=user_input["grid_free_enabled"],
                    grid_cheap_enabled=user_input["grid_cheap_enabled"],
                    grid_normal_enabled=user_input["grid_normal_enabled"],
                    grid_expensive_enabled=user_input["grid_expensive_enabled"],
                ),
            )
            loads = list(self.config_entry.options.get(CONF_LOADS, []))
            loads.append(load_config_to_dict(load))
            options = dict(self.config_entry.options)
            options[CONF_LOADS] = loads
            return self.async_create_entry(title="", data=options)

        return self.async_show_form(step_id="add_load", data_schema=LOAD_SCHEMA)

    async def async_step_remove_load(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        loads = self.config_entry.options.get(CONF_LOADS, [])
        if not loads:
            return self.async_create_entry(title="", data={CONF_LOADS: []})

        if user_input is not None:
            load_id = user_input[CONF_LOAD_ID]
            loads = [load for load in loads if load.get(CONF_LOAD_ID) != load_id]
            options = dict(self.config_entry.options)
            options[CONF_LOADS] = loads
            return self.async_create_entry(title="", data=options)

        options = {
            load.get(CONF_LOAD_NAME, load.get(CONF_LOAD_ID)): load.get(CONF_LOAD_ID)
            for load in loads
        }
        return self.async_show_form(
            step_id="remove_load",
            data_schema=vol.Schema({vol.Required(CONF_LOAD_ID): vol.In(options)}),
        )


@callback
def async_get_options_flow(
    config_entry: config_entries.ConfigEntry,
) -> EnergyDispatcherOptionsFlow:
    return EnergyDispatcherOptionsFlow(config_entry)


def _slugify(value: str) -> str:
    slug = value.strip().lower().replace(" ", "_")
    allowed = "".join(ch for ch in slug if ch.isalnum() or ch == "_")
    return allowed or str(uuid.uuid4())[:8]


def _load_id_exists(entry: config_entries.ConfigEntry, load_id: str) -> bool:
    return any(
        load.get(CONF_LOAD_ID) == load_id for load in entry.options.get(CONF_LOADS, [])
    )
