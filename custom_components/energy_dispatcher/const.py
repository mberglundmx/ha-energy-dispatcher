"""Constants for the Energy Dispatcher integration."""

DOMAIN = "energy_dispatcher"

PLATFORMS = ["load"]
SUBENTRY_TYPE_LOAD = "load"

CONF_PRICE_SENSOR = "price_sensor"
CONF_GRID_INPUT_SENSOR = "grid_input_sensor"
CONF_GRID_OUTPUT_SENSOR = "grid_output_sensor"
CONF_GRID_IMPORT_POWER_SENSOR = "grid_import_power_sensor"  # legacy alias
CONF_EXPORT_PRICE_OFFSET = "export_price_offset"
CONF_GRID_POWER_SENSOR = "grid_power_sensor"  # legacy alias
CONF_POWER_GUARD_STRATEGY = "power_guard_strategy"
CONF_POWER_GUARD_HOURLY_LIMIT_KWH = "power_guard_hourly_limit_kwh"
CONF_PRICE_FREE_THRESHOLD = "price_free_threshold"
CONF_PRICE_CHEAP_RATIO = "price_cheap_ratio"
CONF_PRICE_EXPENSIVE_RATIO = "price_expensive_ratio"
CONF_LOADS = "loads"

CONF_LOAD_ID = "load_id"
CONF_LOAD_NAME = "name"
CONF_REQUIRED_POWER = "required_power"
CONF_ALLOWED_SOURCES = "allowed_sources"

CONF_SOURCE_SOLAR = "solar"
CONF_SOURCE_GRID_FREE = "grid_free"
CONF_SOURCE_GRID_CHEAP = "grid_cheap"
CONF_SOURCE_GRID_NORMAL = "grid_normal"
CONF_SOURCE_GRID_EXPENSIVE = "grid_expensive"

CONF_MINIMUM_SURPLUS = "minimum_surplus"
CONF_MAX_EXPORT_PRICE = "max_export_price"

DEFAULT_PRICE_FREE_THRESHOLD = 0.02
DEFAULT_EXPORT_PRICE_OFFSET = 0.0
DEFAULT_PRICE_CHEAP_RATIO = 0.3
DEFAULT_PRICE_EXPENSIVE_RATIO = 1.5
DEFAULT_POWER_GUARD_HOURLY_LIMIT_KWH = 2.0
DEFAULT_SCAN_INTERVAL = 60

POWER_GUARD_STRATEGY_NONE = "none"
POWER_GUARD_STRATEGY_SIMPLE_THRESHOLD = "simple_threshold"
POWER_GUARD_STRATEGY_ELLEVIO = "ellevio"

STATE_ON = "ON"
STATE_OFF = "OFF"

ENERGY_MODE_SOLAR = "SOLAR"
ENERGY_MODE_GRID_FREE = "GRID_FREE"
ENERGY_MODE_GRID_CHEAP = "GRID_CHEAP"
ENERGY_MODE_GRID_NORMAL = "GRID_NORMAL"
ENERGY_MODE_GRID_EXPENSIVE = "GRID_EXPENSIVE"
ENERGY_MODE_BLOCKED = "BLOCKED"

GRID_STATE_NORMAL = "NORMAL"
GRID_STATE_WARNING = "WARNING"
GRID_STATE_CRITICAL = "CRITICAL"

PRICE_STATE_LOW = "LOW"
PRICE_STATE_NORMAL = "NORMAL"
PRICE_STATE_HIGH = "HIGH"

SERVICE_OVERRIDE = "override"
SERVICE_CLEAR_OVERRIDE = "clear_override"
SERVICE_RECALCULATE = "recalculate"

ATTR_ENERGY_MODE = "energy_mode"
ATTR_REASON = "reason"
ATTR_REASON_TEXT = "reason_text"
ATTR_AVAILABLE_POWER = "available_power"
ATTR_REQUIRED_POWER = "required_power"
ATTR_PRICE_STATE = "price_state"
ATTR_GRID_STATE = "grid_state"
ATTR_NEXT_OPPORTUNITY = "next_opportunity"
ATTR_POWER_GUARD_STRATEGY = "power_guard_strategy"
ATTR_POWER_GUARD_PEAK_AVERAGE = "power_guard_peak_average"
ATTR_POWER_GUARD_HEADROOM = "power_guard_headroom"
ATTR_POWER_GUARD_BILLING_PERIOD = "power_guard_billing_period"
ATTR_POWER_GUARD_IMPORT_POWER = "power_guard_import_power"
ATTR_POWER_GUARD_HOUR_KWH = "power_guard_hour_kwh"
ATTR_POWER_GUARD_PROJECTED_HOUR_KWH = "power_guard_projected_hour_kwh"
ATTR_POWER_GUARD_HOURLY_LIMIT_KWH = "power_guard_hourly_limit_kwh"
ATTR_RUNTIME_REMAINING_MINUTES = "runtime_remaining_minutes"
ATTR_RUNTIME_MINUTES_TODAY = "runtime_minutes_today"
ATTR_RUNTIME_MINUTES_WEEK = "runtime_minutes_week"

REASON_GRID_EXPORT = "grid_export"
REASON_GRID_FREE = "grid_free"
REASON_GRID_CHEAP = "grid_cheap"
REASON_GRID_NORMAL = "grid_normal"
REASON_NOT_CHEAP_YET = "not_cheap_yet"
REASON_NOT_ALLOWED = "not_allowed"
REASON_POWER_GUARD = "power_guard"
REASON_OVERRIDE = "override"
REASON_NO_SOURCE = "no_source"
REASON_RUNTIME_REQUIRED = "runtime_required"
