"""Cover platform for RFLink UI.

Based on the work of @bazeman101 in guanaco0403/Home-Assistant-Rflink-UI#14.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
    CoverState,
)
from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    COMMANDS_OFF,
    COMMANDS_ON,
    CONF_INVERTED,
    DOMAIN,
    SUBENTRY_TYPE_COVER,
)
from .entity import RFLinkEntity
from .gateway import RFLinkConfigEntry, RFLinkGateway
from .protocol import RFLinkPacket

_INVERSE_COMMAND = {"UP": "DOWN", "DOWN": "UP"}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RFLinkConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the RFLink cover platform."""

    @callback
    def _build(gateway: RFLinkGateway, subentry: ConfigSubentry) -> list[CoverEntity]:
        return [RFLinkCover(gateway, subentry)]

    entry.runtime_data.async_register_platform(
        SUBENTRY_TYPE_COVER, async_add_entities, _build
    )


class RFLinkCover(RFLinkEntity, CoverEntity, RestoreEntity):
    """A roller shutter or blind controlled through the RFLink gateway."""

    _attr_name = None
    _attr_assumed_state = True
    _attr_device_class = CoverDeviceClass.SHUTTER
    _attr_supported_features = (
        CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
    )

    def __init__(self, gateway: RFLinkGateway, subentry: ConfigSubentry) -> None:
        """Initialize the cover."""
        super().__init__(gateway, subentry)
        self._inverted = bool(subentry.data.get(CONF_INVERTED, False))
        self._attr_unique_id = f"rflink_cover_{self._device_id}"
        self._is_open = False

    @property
    def is_closed(self) -> bool:
        """Return whether the cover is closed."""
        return not self._is_open

    async def async_added_to_hass(self) -> None:
        """Restore the previous state."""
        await super().async_added_to_hass()
        if (state := await self.async_get_last_state()) is not None:
            self._is_open = state.state == CoverState.OPEN

    @callback
    def async_handle_packet(self, packet: RFLinkPacket) -> None:
        """Update the state when a physical remote is used."""
        command = packet.command
        # STOP carries no definitive open/closed state, so it is ignored.
        if command in COMMANDS_ON:
            self._is_open = not self._inverted
        elif command in COMMANDS_OFF:
            self._is_open = self._inverted
        else:
            return

        self._attr_available = True
        self.async_write_ha_state()

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        await self._async_send(self._wire_command("UP"))
        self._is_open = True
        self.async_write_ha_state()

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        await self._async_send(self._wire_command("DOWN"))
        self._is_open = False
        self.async_write_ha_state()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover; protocols without STOP simply ignore the command."""
        await self._async_send("STOP")

    def _wire_command(self, command: str) -> str:
        """Swap UP/DOWN for protocols that have them reversed."""
        if not self._inverted:
            return command
        return _INVERSE_COMMAND.get(command, command)

    async def _async_send(self, command: str) -> None:
        try:
            await self.async_send_command(command)
        except (ConnectionError, OSError) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="send_failed",
                translation_placeholders={"error": str(err)},
            ) from err
