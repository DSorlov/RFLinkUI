"""Radio frequency transmitter platform for RFLink UI."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.radio_frequency import (
    RadioFrequencyCommand,
    RadioFrequencyTransmitterEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
import voluptuous as vol

from .const import (
    ATTR_COMMAND,
    ATTR_PACKET,
    ATTR_PROTOCOL,
    DOMAIN,
    SERVICE_SEND_COMMAND,
    SERVICE_SEND_RAW,
    SIGNAL_CONNECTION,
)
from .gateway import RFLinkConfigEntry, RFLinkGateway

_LOGGER = logging.getLogger(__name__)

#: RFLink gateways are 433.92 MHz OOK transceivers.
FREQUENCY_HZ = 433_920_000


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RFLinkConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the RFLink transmitter entity and its actions."""
    async_add_entities([RFLinkTransmitter(entry.runtime_data)])

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_SEND_COMMAND,
        {
            vol.Required(ATTR_PROTOCOL): cv.string,
            vol.Required(ATTR_COMMAND): cv.string,
        },
        "async_send_rflink_command",
    )
    platform.async_register_entity_service(
        SERVICE_SEND_RAW,
        {vol.Required(ATTR_PACKET): cv.string},
        "async_send_rflink_raw",
    )


class RFLinkTransmitter(RadioFrequencyTransmitterEntity):
    """The transmitter side of an RFLink gateway."""

    _attr_has_entity_name = True
    _attr_translation_key = "transmitter"
    _attr_should_poll = False

    def __init__(self, gateway: RFLinkGateway) -> None:
        """Initialize the transmitter."""
        self._gateway = gateway
        self._attr_unique_id = f"{gateway.entry.entry_id}_rf_transmitter"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, gateway.entry.entry_id)},
            name=gateway.entry.title,
            manufacturer="RFLink",
            model="Arduino RFLink",
            serial_number=gateway.port,
        )

    @property
    def supported_frequency_ranges(self) -> list[tuple[int, int]]:
        """Return the frequency range this gateway can transmit on."""
        return [(FREQUENCY_HZ, FREQUENCY_HZ)]

    @property
    def available(self) -> bool:
        """Return whether the gateway is reachable."""
        return self._gateway.is_connected

    async def async_added_to_hass(self) -> None:
        """Track the gateway connection state."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_CONNECTION.format(self._gateway.entry.entry_id),
                self._handle_connection,
            )
        )

    @callback
    def _handle_connection(self, connected: bool) -> None:
        self.async_write_ha_state()

    async def async_send_command(self, command: RadioFrequencyCommand) -> None:
        """Raw timing based transmission is not supported by RFLink."""
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="raw_timings_unsupported",
        )

    async def async_send_rflink_command(
        self, protocol: str, command: str, **kwargs: Any
    ) -> None:
        """Send a protocol command, for example ``Unitec`` / ``1a4a;4;ON``."""
        await self.async_send_rflink_raw(f"10;{protocol};{command};")

    async def async_send_rflink_raw(self, packet: str, **kwargs: Any) -> None:
        """Send a complete packet such as ``10;GPIOset;32;0;ON;``."""
        try:
            await self._gateway.async_send_raw(packet)
        except (ConnectionError, OSError) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="send_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        self.async_write_ha_state()
