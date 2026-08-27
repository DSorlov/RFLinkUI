"""Light platform for RFLink UI."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.config_entries import ConfigSubentry
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    COMMANDS_OFF,
    COMMANDS_ON,
    CONF_LIGHT_TYPE,
    DOMAIN,
    LIGHT_TYPE_DIMMABLE,
    LIGHT_TYPE_HYBRID,
    LIGHT_TYPE_SWITCHABLE,
    LIGHT_TYPE_TOGGLE,
    SUBENTRY_TYPE_LIGHT,
)
from .entity import RFLinkEntity
from .gateway import RFLinkConfigEntry, RFLinkGateway
from .protocol import RFLinkPacket

#: RFLink dim levels run from 0 to 15.
_MAX_LEVEL = 15
_DIMMABLE_TYPES = (LIGHT_TYPE_DIMMABLE, LIGHT_TYPE_HYBRID)


def _level_to_brightness(level: int) -> int:
    return min(255, round(level * 255 / _MAX_LEVEL))


def _brightness_to_level(brightness: int) -> int:
    return max(1, min(_MAX_LEVEL, round(brightness * _MAX_LEVEL / 255)))


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RFLinkConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the RFLink light platform."""

    @callback
    def _build(gateway: RFLinkGateway, subentry: ConfigSubentry) -> list[LightEntity]:
        return [RFLinkLight(gateway, subentry)]

    entry.runtime_data.async_register_platform(
        SUBENTRY_TYPE_LIGHT, async_add_entities, _build
    )


class RFLinkLight(RFLinkEntity, LightEntity, RestoreEntity):
    """A light or dimmer controlled through the RFLink gateway."""

    _attr_name = None
    _attr_assumed_state = True

    def __init__(self, gateway: RFLinkGateway, subentry: ConfigSubentry) -> None:
        """Initialize the light."""
        super().__init__(gateway, subentry)
        self._light_type: str = subentry.data.get(CONF_LIGHT_TYPE, LIGHT_TYPE_DIMMABLE)
        self._attr_unique_id = f"rflink_light_{self._device_id}"
        self._attr_is_on = False

        if self._light_type in _DIMMABLE_TYPES:
            self._attr_color_mode = ColorMode.BRIGHTNESS
            self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
            self._attr_brightness = 255
        else:
            self._attr_color_mode = ColorMode.ONOFF
            self._attr_supported_color_modes = {ColorMode.ONOFF}

    async def async_added_to_hass(self) -> None:
        """Restore the previous state."""
        await super().async_added_to_hass()
        if (state := await self.async_get_last_state()) is None:
            return
        self._attr_is_on = state.state == STATE_ON
        if self._light_type in _DIMMABLE_TYPES and (
            brightness := state.attributes.get(ATTR_BRIGHTNESS)
        ):
            self._attr_brightness = int(brightness)

    @callback
    def async_handle_packet(self, packet: RFLinkPacket) -> None:
        """Update the state from a received command."""
        command = packet.command
        if command is None:
            return

        self._attr_available = True

        if self._light_type == LIGHT_TYPE_TOGGLE:
            if command in COMMANDS_ON:
                self._attr_is_on = not self._attr_is_on
            self.async_write_ha_state()
            return

        raw_level = packet.fields.get("SET_LEVEL")
        if raw_level is None and command.isdigit():
            raw_level = command

        if raw_level is not None:
            try:
                level = int(raw_level)
            except ValueError:
                return
            if self._light_type in _DIMMABLE_TYPES:
                self._attr_brightness = _level_to_brightness(level)
            self._attr_is_on = level > 0
        elif command in COMMANDS_ON:
            self._attr_is_on = True
        elif command in COMMANDS_OFF:
            self._attr_is_on = False
        else:
            return

        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on, optionally at a given brightness."""
        if self._light_type == LIGHT_TYPE_TOGGLE:
            await self._async_send("ON")
            self._attr_is_on = not self._attr_is_on
            self.async_write_ha_state()
            return

        brightness = kwargs.get(ATTR_BRIGHTNESS)
        if brightness is not None and self._light_type in _DIMMABLE_TYPES:
            level = _brightness_to_level(brightness)
            self._attr_brightness = _level_to_brightness(level)
            await self._async_send(str(level))

        if brightness is None or self._light_type in (
            LIGHT_TYPE_HYBRID,
            LIGHT_TYPE_SWITCHABLE,
        ):
            await self._async_send("ON")

        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        await self._async_send("ON" if self._light_type == LIGHT_TYPE_TOGGLE else "OFF")
        self._attr_is_on = (
            not self._attr_is_on if self._light_type == LIGHT_TYPE_TOGGLE else False
        )
        self.async_write_ha_state()

    async def _async_send(self, command: str) -> None:
        try:
            await self.async_send_command(command)
        except (ConnectionError, OSError) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="send_failed",
                translation_placeholders={"error": str(err)},
            ) from err
