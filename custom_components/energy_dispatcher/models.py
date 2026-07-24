"""Data models for the Energy Dispatcher integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from .power_guard import PowerGuardState

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigSubentry

from .const import POWER_MODE_FIXED, POWER_MODE_SENSOR


@dataclass(frozen=True)
class PriceSlot:
    """A single price point in the timeline."""

    start: datetime
    price: float


@dataclass(frozen=True)
class PriceThresholds:
    """User-configured price classification thresholds."""

    free_threshold: float
    cheap_ratio: float
    expensive_ratio: float


@dataclass(frozen=True)
class SourceRules:
    """Allowed energy source rules for a load."""

    solar_enabled: bool = False
    solar_max_export_price: float | None = None
    grid_free_enabled: bool = False
    grid_cheap_enabled: bool = False
    grid_normal_enabled: bool = False
    grid_expensive_enabled: bool = False


@dataclass(frozen=True)
class LoadConfig:
    """Configuration for a single dispatch target."""

    load_id: str
    name: str
    sources: SourceRules
    power_mode: str = POWER_MODE_FIXED
    required_power: float | None = None
    power_sensor: str | None = None
    minimum_minutes_per_day: int | None = None
    minimum_minutes_per_week: int | None = None


@dataclass(frozen=True)
class LoadPowerSnapshot:
    """Resolved power requirement/measurement for one evaluation."""

    power_mode: str
    power_learning: str
    effective_required_power: float | None
    measured_power: float
    learned_required_power: float | None = None


@dataclass(frozen=True)
class GlobalState:
    """Shared state derived from input sensors."""

    now: datetime
    grid_input: float | None
    grid_output: float | None
    export_price: float | None
    price_timeline: tuple[PriceSlot, ...]
    rolling_average_price: float | None
    power_guard: PowerGuardState
    price_thresholds: PriceThresholds


@dataclass(frozen=True)
class OverrideState:
    """Manual override for a load."""

    mode: str
    expires_at: datetime


@dataclass(frozen=True)
class Decision:
    """Result of the decision engine for one load."""

    state: str
    energy_mode: str
    reason: str
    reason_text: str
    available_power: float
    required_power: float
    price_state: str
    grid_state: str
    next_opportunity: datetime | None = None


@dataclass
class LoadRuntimeState:
    """Mutable runtime state for a load entity."""

    override: OverrideState | None = None
    last_decision: Decision | None = None


def load_config_from_dict(data: dict[str, Any]) -> LoadConfig:
    """Build a LoadConfig from stored options data."""
    sources_data = data.get("allowed_sources", {})
    solar = sources_data.get("solar", {})
    power_mode = data.get("power_mode", POWER_MODE_FIXED)
    if power_mode not in (POWER_MODE_FIXED, POWER_MODE_SENSOR):
        power_mode = POWER_MODE_FIXED
    required_power = _optional_float(data.get("required_power"))
    power_sensor = data.get("power_sensor") or None
    # Legacy entries always had required_power and no power_mode.
    if power_mode == POWER_MODE_FIXED and required_power is None:
        required_power = 0.0
    if power_mode == POWER_MODE_SENSOR:
        required_power = None
    return LoadConfig(
        load_id=data["load_id"],
        name=data["name"],
        power_mode=power_mode,
        required_power=required_power,
        power_sensor=power_sensor if power_mode == POWER_MODE_SENSOR else None,
        sources=SourceRules(
            solar_enabled=bool(solar.get("enabled", False)),
            solar_max_export_price=_optional_float(solar.get("max_export_price")),
            grid_free_enabled=bool(sources_data.get("grid_free", {}).get("enabled", False)),
            grid_cheap_enabled=bool(sources_data.get("grid_cheap", {}).get("enabled", False)),
            grid_normal_enabled=bool(sources_data.get("grid_normal", {}).get("enabled", False)),
            grid_expensive_enabled=bool(
                sources_data.get("grid_expensive", {}).get("enabled", False)
            ),
        ),
        minimum_minutes_per_day=_optional_int(data.get("minimum_minutes_per_day")),
        minimum_minutes_per_week=_optional_int(data.get("minimum_minutes_per_week")),
    )


def load_config_from_subentry(subentry: ConfigSubentry) -> LoadConfig:
    """Build a LoadConfig from a config subentry."""
    data = dict(subentry.data)
    data["load_id"] = subentry.unique_id or subentry.title
    data["name"] = subentry.title
    return load_config_from_dict(data)


def load_config_to_subentry_data(config: LoadConfig) -> dict[str, Any]:
    """Serialize load settings for storage in a config subentry."""
    data = load_config_to_dict(config)
    data.pop("load_id")
    data.pop("name")
    return data


def load_config_to_dict(config: LoadConfig) -> dict[str, Any]:
    """Serialize a LoadConfig for storage."""
    return {
        "load_id": config.load_id,
        "name": config.name,
        "power_mode": config.power_mode,
        "required_power": config.required_power,
        "power_sensor": config.power_sensor,
        "minimum_minutes_per_day": config.minimum_minutes_per_day,
        "minimum_minutes_per_week": config.minimum_minutes_per_week,
        "allowed_sources": {
            "solar": {
                "enabled": config.sources.solar_enabled,
                "max_export_price": config.sources.solar_max_export_price,
            },
            "grid_free": {"enabled": config.sources.grid_free_enabled},
            "grid_cheap": {"enabled": config.sources.grid_cheap_enabled},
            "grid_normal": {"enabled": config.sources.grid_normal_enabled},
            "grid_expensive": {"enabled": config.sources.grid_expensive_enabled},
        },
    }


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)
