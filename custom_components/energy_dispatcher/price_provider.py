"""Normalize price sensor data into a uniform timeline."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .models import PriceSlot

_LOGGER = logging.getLogger(__name__)

ATTR_RAW_TODAY = "raw_today"
ATTR_RAW_TOMORROW = "raw_tomorrow"
ATTR_TODAY = "today"
ATTR_TOMORROW = "tomorrow"
ATTR_PRICES = "prices"


class PriceProvider:
    """Read and normalize price data from a Home Assistant sensor entity."""

    def __init__(self, hass: HomeAssistant, entity_id: str) -> None:
        self._hass = hass
        self._entity_id = entity_id

    def get_timeline(self, now: datetime | None = None) -> tuple[PriceSlot, ...]:
        """Return all available hourly price slots from the configured sensor."""
        now = now or dt_util.now()
        state = self._hass.states.get(self._entity_id)
        if state is None or state.state in ("unknown", "unavailable", None, ""):
            _LOGGER.debug("Price sensor %s unavailable", self._entity_id)
            return ()

        slots: list[PriceSlot] = []
        attrs = state.attributes

        for attr in (ATTR_RAW_TODAY, ATTR_RAW_TOMORROW, ATTR_TODAY, ATTR_TOMORROW, ATTR_PRICES):
            if attr not in attrs:
                continue
            parsed = _parse_price_mapping(attrs[attr], now, attr)
            if parsed:
                slots.extend(parsed)
                break

        if not slots:
            current = _try_float(state.state)
            if current is not None:
                slot_start = now.replace(minute=0, second=0, microsecond=0)
                slots.append(PriceSlot(start=slot_start, price=current))

        return tuple(_deduplicate_slots(slots))


def _parse_price_mapping(
    data: Any, now: datetime, attr_name: str
) -> list[PriceSlot]:
    """Parse common dict/list price attribute formats."""
    if isinstance(data, dict):
        return _parse_price_dict(data, now)
    if isinstance(data, list):
        return _parse_price_list(data, now, attr_name)
    return []


def _parse_price_dict(data: dict[Any, Any], now: datetime) -> list[PriceSlot]:
    slots: list[PriceSlot] = []
    for key, value in data.items():
        price = _try_float(value)
        if price is None:
            continue
        start = _parse_time_key(key, now)
        if start is not None:
            slots.append(PriceSlot(start=start, price=price))
    return sorted(slots, key=lambda slot: slot.start)


def _parse_price_list(data: list[Any], now: datetime, attr_name: str) -> list[PriceSlot]:
    slots: list[PriceSlot] = []
    day_offset = 1 if "tomorrow" in attr_name else 0
    base = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=day_offset)

    for index, item in enumerate(data):
        if isinstance(item, dict):
            price = _try_float(item.get("price", item.get("value")))
            start_raw = item.get("start") or item.get("time") or item.get("hour")
            if price is None:
                continue
            if start_raw is not None:
                start = _parse_time_key(start_raw, now)
                if start is None:
                    start = base + timedelta(hours=index)
            else:
                start = base + timedelta(hours=index)
            slots.append(PriceSlot(start=start, price=price))
        else:
            price = _try_float(item)
            if price is not None:
                slots.append(PriceSlot(start=base + timedelta(hours=index), price=price))
    return sorted(slots, key=lambda slot: slot.start)


def _parse_time_key(key: Any, now: datetime) -> datetime | None:
    if isinstance(key, datetime):
        return dt_util.as_local(key) if key.tzinfo else key.replace(tzinfo=now.tzinfo)

    text = str(key)
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%H:%M:%S",
        "%H:%M",
    ):
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if parsed.year == 1900:
            parsed = now.replace(
                hour=parsed.hour,
                minute=parsed.minute,
                second=parsed.second,
                microsecond=0,
            )
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=now.tzinfo)
        return parsed

    return None


def _try_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _deduplicate_slots(slots: list[PriceSlot]) -> list[PriceSlot]:
    seen: dict[datetime, PriceSlot] = {}
    for slot in sorted(slots, key=lambda item: item.start):
        seen[slot.start] = slot
    return list(seen.values())
