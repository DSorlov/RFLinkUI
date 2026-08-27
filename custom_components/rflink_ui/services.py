"""Services for the RFLink UI integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import ConfigEntrySelector
import voluptuous as vol

from .const import ATTR_PACKET, DOMAIN, SERVICE_SIMULATE_PACKET

ATTR_CONFIG_ENTRY_ID = "config_entry_id"

SIMULATE_PACKET_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_PACKET): cv.string,
        vol.Optional(ATTR_CONFIG_ENTRY_ID): ConfigEntrySelector(
            {"integration": DOMAIN}
        ),
    }
)


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration wide services."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_SIMULATE_PACKET,
        _async_simulate_packet,
        schema=SIMULATE_PACKET_SCHEMA,
    )


async def _async_simulate_packet(call: ServiceCall) -> None:
    """Feed a raw packet into one or all configured gateways."""
    hass = call.hass
    entry_id = call.data.get(ATTR_CONFIG_ENTRY_ID)

    entries = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
        and (entry_id is None or entry.entry_id == entry_id)
    ]
    if not entries:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="no_loaded_gateway"
        )

    for entry in entries:
        entry.runtime_data.async_handle_line(call.data[ATTR_PACKET])
