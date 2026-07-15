"""Config flow for Energy Dispatcher."""

from __future__ import annotations

from typing import Any
import uuid

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigSubentryFlow, SubentryFlowResult
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_EXPORT_PRICE_OFFSET,
    CONF_GRID_INPUT_SENSOR,
    CONF_GRID_OUTPUT_SENSOR,
    CONF_LOAD_NAME,
    CONF_POWER_GUARD_HOURLY_LIMIT_KWH,
    CONF_POWER_GUARD_STRATEGY,
    CONF_PRICE_CHEAP_RATIO,
    CONF_PRICE_EXPENSIVE_RATIO,
    CONF_PRICE_FREE_THRESHOLD,
    CONF_PRICE_SENSOR,
    CONF_REQUIRED_POWER,
    DEFAULT_EXPORT_PRICE_OFFSET,
    DEFAULT_POWER_GUARD_HOURLY_LIMIT_KWH,
    DEFAULT_PRICE_CHEAP_RATIO,
    DEFAULT_PRICE_EXPENSIVE_RATIO,
    DEFAULT_PRICE_FREE_THRESHOLD,
    DOMAIN,
    POWER_GUARD_STRATEGY_NONE,
    POWER_GUARD_STRATEGY_SIMPLE_THRESHOLD,
    SUBENTRY_TYPE_LOAD,
)
from .models import (
    LoadConfig,
    SourceRules,
    load_config_from_subentry,
    load_config_to_subentry_data,
)

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
        vol.Required(
            CONF_EXPORT_PRICE_OFFSET, default=DEFAULT_EXPORT_PRICE_OFFSET
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0,
                step=0.01,
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
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
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0.1,
                step=0.1,
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Optional(CONF_PRICE_FREE_THRESHOLD, default=DEFAULT_PRICE_FREE_THRESHOLD): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0,
                step=0.01,
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Optional(CONF_PRICE_CHEAP_RATIO, default=DEFAULT_PRICE_CHEAP_RATIO): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0,
                max=1,
                step=0.05,
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Optional(
            CONF_PRICE_EXPENSIVE_RATIO, default=DEFAULT_PRICE_EXPENSIVE_RATIO
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1,
                step=0.1,
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
    }
)

LOAD_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_LOAD_NAME): str,
        vol.Required(CONF_REQUIRED_POWER): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1,
                step=100,
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Required("solar_enabled", default=True): bool,
        vol.Optional("solar_max_export_price"): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0,
                step=0.01,
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Optional("minimum_minutes_per_day"): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0,
                step=15,
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Optional("minimum_minutes_per_week"): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0,
                step=15,
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Required("grid_free_enabled", default=False): bool,
        vol.Required("grid_cheap_enabled", default=True): bool,
        vol.Required("grid_normal_enabled", default=False): bool,
        vol.Required("grid_expensive_enabled", default=False): bool,
    }
)


class EnergyDispatcherConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Energy Dispatcher."""

    VERSION = 2

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: config_entries.ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return subentries supported by this integration."""
        return {SUBENTRY_TYPE_LOAD: LoadSubentryFlowHandler}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title="Energy Dispatcher", data=user_input)

        return self.async_show_form(step_id="user", data_schema=STEP_USER_SCHEMA)


class LoadSubentryFlowHandler(ConfigSubentryFlow):
    """Handle subentry flow for adding and modifying loads."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Add a load subentry."""
        return await self._async_step_load(user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Reconfigure an existing load subentry."""
        return await self._async_step_load(user_input, is_reconfigure=True)

    async def _async_step_load(
        self,
        user_input: dict[str, Any] | None = None,
        *,
        is_reconfigure: bool = False,
    ) -> SubentryFlowResult:
        subentry = self._get_reconfigure_subentry() if is_reconfigure else None

        if user_input is not None:
            load_id = _slugify(user_input[CONF_LOAD_NAME])
            if is_reconfigure:
                assert subentry is not None
                if load_id != subentry.unique_id and _subentry_id_exists(
                    self._get_entry(), load_id
                ):
                    return self.async_show_form(
                        step_id="reconfigure" if is_reconfigure else "user",
                        data_schema=LOAD_SCHEMA,
                        errors={"base": "load_exists"},
                    )
                load = _load_from_user_input(user_input, subentry.unique_id or load_id)
                return self.async_update_and_abort(
                    self._get_entry(),
                    subentry,
                    title=user_input[CONF_LOAD_NAME],
                    data=load_config_to_subentry_data(load),
                )

            if _subentry_id_exists(self._get_entry(), load_id):
                return self.async_show_form(
                    step_id="user",
                    data_schema=LOAD_SCHEMA,
                    errors={"base": "load_exists"},
                )
            load = _load_from_user_input(user_input, load_id)
            return self.async_create_entry(
                title=user_input[CONF_LOAD_NAME],
                data=load_config_to_subentry_data(load),
                unique_id=load_id,
            )

        defaults: dict[str, Any] = {}
        if subentry is not None:
            load = load_config_from_subentry(subentry)
            defaults = {
                CONF_LOAD_NAME: load.name,
                CONF_REQUIRED_POWER: load.required_power,
                "solar_enabled": load.sources.solar_enabled,
                "solar_max_export_price": load.sources.solar_max_export_price,
                "minimum_minutes_per_day": load.minimum_minutes_per_day,
                "minimum_minutes_per_week": load.minimum_minutes_per_week,
                "grid_free_enabled": load.sources.grid_free_enabled,
                "grid_cheap_enabled": load.sources.grid_cheap_enabled,
                "grid_normal_enabled": load.sources.grid_normal_enabled,
                "grid_expensive_enabled": load.sources.grid_expensive_enabled,
            }

        step_id = "reconfigure" if is_reconfigure else "user"
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(LOAD_SCHEMA, defaults),
        )


def _load_from_user_input(user_input: dict[str, Any], load_id: str) -> LoadConfig:
    return LoadConfig(
        load_id=load_id,
        name=user_input[CONF_LOAD_NAME],
        required_power=float(user_input[CONF_REQUIRED_POWER]),
        minimum_minutes_per_day=_optional_int(user_input.get("minimum_minutes_per_day")),
        minimum_minutes_per_week=_optional_int(user_input.get("minimum_minutes_per_week")),
        sources=SourceRules(
            solar_enabled=user_input["solar_enabled"],
            solar_max_export_price=_optional_float(user_input.get("solar_max_export_price")),
            grid_free_enabled=user_input["grid_free_enabled"],
            grid_cheap_enabled=user_input["grid_cheap_enabled"],
            grid_normal_enabled=user_input["grid_normal_enabled"],
            grid_expensive_enabled=user_input["grid_expensive_enabled"],
        ),
    )


def _subentry_id_exists(entry: config_entries.ConfigEntry, load_id: str) -> bool:
    return any(
        subentry.unique_id == load_id and subentry.subentry_type == SUBENTRY_TYPE_LOAD
        for subentry in entry.subentries.values()
    )


def _slugify(value: str) -> str:
    slug = value.strip().lower().replace(" ", "_")
    allowed = "".join(ch for ch in slug if ch.isalnum() or ch == "_")
    return allowed or str(uuid.uuid4())[:8]


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)
