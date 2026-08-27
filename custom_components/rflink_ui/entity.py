"""Base entity for the RFLink UI integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import (
    CONF_ALIASES,
    CONF_DEVICE_ID,
    DOMAIN,
    SIGNAL_CONNECTION,
    SIGNAL_DEVICE_UPDATE,
    SIGNAL_GROUP_UPDATE,
)
from .gateway import RFLinkGateway
from .protocol import RFLinkPacket, split_device_id


class RFLinkEntity(Entity):
    """Common behaviour for every entity backed by an RFLink device."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    #: Whether the device id carries a trailing switch/button component.
    has_switch_component = True

    def __init__(
        self,
        gateway: RFLinkGateway,
        subentry: ConfigSubentry,
        initial_packet: RFLinkPacket | None = None,
    ) -> None:
        """Initialize the entity."""
        self.gateway = gateway
        self.subentry = subentry
        self._initial_packet = initial_packet
        self._device_id: str = subentry.data[CONF_DEVICE_ID]
        self._aliases: list[str] = list(subentry.data.get(CONF_ALIASES, []))
        self._protocol, self._rflink_id, self._rflink_switch = split_device_id(
            self._device_id, with_switch=self.has_switch_component
        )
        self._attr_available = gateway.is_connected
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=subentry.title,
            manufacturer="RFLink",
            model=self._protocol,
            via_device=(DOMAIN, gateway.entry.entry_id),
        )

    @property
    def _group_ids(self) -> list[str]:
        """Return the group ids this entity reacts to for ALLON/ALLOFF."""
        if not self.has_switch_component:
            return []
        groups = [f"{self._protocol}_{self._rflink_id}"]
        for alias in self._aliases:
            protocol, ident, _ = split_device_id(alias, with_switch=True)
            groups.append(f"{protocol}_{ident}")
        return groups

    async def async_added_to_hass(self) -> None:
        """Subscribe to gateway updates."""
        await super().async_added_to_hass()
        entry_id = self.gateway.entry.entry_id

        for device_id in (self._device_id, *self._aliases):
            self.async_on_remove(
                async_dispatcher_connect(
                    self.hass,
                    SIGNAL_DEVICE_UPDATE.format(entry_id, device_id),
                    self._async_dispatch_packet,
                )
            )

        for group_id in self._group_ids:
            self.async_on_remove(
                async_dispatcher_connect(
                    self.hass,
                    SIGNAL_GROUP_UPDATE.format(entry_id, group_id),
                    self._async_dispatch_packet,
                )
            )

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_CONNECTION.format(entry_id),
                self._async_handle_connection,
            )
        )

        if self._initial_packet is not None:
            packet, self._initial_packet = self._initial_packet, None
            self.async_handle_packet(packet)

    @callback
    def _async_dispatch_packet(self, packet: RFLinkPacket) -> None:
        """Handle an incoming packet for this device."""
        self.async_handle_packet(packet)

    @callback
    def async_handle_packet(self, packet: RFLinkPacket) -> None:
        """Process a packet addressed to this entity."""
        raise NotImplementedError

    @callback
    def _async_handle_connection(self, connected: bool) -> None:
        """Track gateway availability."""
        self._attr_available = connected
        self.async_write_ha_state()

    async def async_send_command(self, command: str) -> None:
        """Send a command to this device."""
        await self.gateway.async_send_command(
            self._protocol, self._rflink_id, self._rflink_switch, command
        )
