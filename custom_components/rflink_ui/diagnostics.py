"""Diagnostics support for RFLink UI."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .gateway import RFLinkConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: RFLinkConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    gateway = entry.runtime_data

    return {
        "entry": {
            "version": entry.version,
            "options": dict(entry.options),
        },
        "gateway": {
            "connected": gateway.is_connected,
            "packets_received": gateway.packets_received,
            "automatic_add": gateway.automatic_add,
            "signal_repetitions": gateway.signal_repetitions,
        },
        "devices": [
            {
                "subentry_type": subentry.subentry_type,
                "title": subentry.title,
                "data": dict(subentry.data),
            }
            for subentry in entry.subentries.values()
        ],
        "seen": [
            {
                "device_id": device.device_id,
                "device_type": device.device_type,
                "protocol": device.protocol,
                "fields": device.fields,
                "last_seen": device.last_seen.isoformat(),
            }
            for device in gateway.seen.values()
        ],
    }
