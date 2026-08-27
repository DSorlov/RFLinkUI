"""Switch platform for RFLink UI."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigSubentry
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import COMMANDS_OFF, COMMANDS_ON, DOMAIN, SUBENTRY_TYPE_SWITCH
from .entity import RFLinkEntity
from .gateway import RFLinkConfigEntry, RFLinkGateway
from .protocol import RFLinkPacket


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RFLinkConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the RFLink switch platform."""

    @callback
    def _build(gateway: RFLinkGateway, subentry: ConfigSubentry) -> list[SwitchEntity]:
        return [RFLinkSwitch(gateway, subentry)]

    entry.runtime_data.async_register_platform(
        SUBENTRY_TYPE_SWITCH, async_add_entities, _build
    )


class RFLinkSwitch(RFLinkEntity, SwitchEntity, RestoreEntity):
    """A switch controlled through the RFLink gateway."""

    _attr_name = None
    _attr_assumed_state = True
    # Repeated identical remote presses must still trigger automations.
    _attr_force_update = True

    def __init__(self, gateway: RFLinkGateway, subentry: ConfigSubentry) -> None:
        """Initialize the switch."""
        super().__init__(gateway, subentry)
        self._attr_unique_id = f"rflink_switch_{self._device_id}"
        self._attr_is_on = False

    async def async_added_to_hass(self) -> None:
        """Restore the previous state."""
        await super().async_added_to_hass()
        if (state := await self.async_get_last_state()) is not None:
            self._attr_is_on = state.state == STATE_ON

    @callback
    def async_handle_packet(self, packet: RFLinkPacket) -> None:
        """Update the state from a received command."""
        command = packet.command
        if command in COMMANDS_ON:
            self._attr_is_on = True
        elif command in COMMANDS_OFF:
            self._attr_is_on = False
        else:
            return

        self._attr_available = True
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self._async_command("ON", True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self._async_command("OFF", False)

    async def _async_command(self, command: str, is_on: bool) -> None:
        try:
            await self.async_send_command(command)
        except (ConnectionError, OSError) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="send_failed",
                translation_placeholders={"error": str(err)},
            ) from err

        self._attr_is_on = is_on
        self.async_write_ha_state()
