"""Binary sensor platform for RFLink UI."""

from __future__ import annotations

from dataclasses import dataclass
import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigSubentry
from homeassistant.const import CONF_DEVICE_CLASS, CONF_PORT, STATE_ON
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    COMMANDS_OFF,
    COMMANDS_ON,
    CONF_OFF_DELAY,
    DOMAIN,
    SIGNAL_CONNECTION,
    SIGNAL_DEVICE_UPDATE,
    SUBENTRY_TYPE_BINARY_SENSOR,
    SUBENTRY_TYPE_SENSOR,
)
from .entity import RFLinkEntity
from .gateway import RFLinkConfigEntry, RFLinkGateway, async_subentry_device_ids
from .protocol import RFLinkPacket

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class RFLinkBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes an RFLink binary sensor derived from a payload field."""

    rflink_key: str


#: RFLink fields that are boolean by nature and get their own entity.
BINARY_SENSOR_TYPES: dict[str, RFLinkBinarySensorEntityDescription] = {
    "PIR": RFLinkBinarySensorEntityDescription(
        rflink_key="PIR",
        key="motion",
        device_class=BinarySensorDeviceClass.MOTION,
    ),
    "SMOKEALERT": RFLinkBinarySensorEntityDescription(
        rflink_key="SMOKEALERT",
        key="smoke",
        device_class=BinarySensorDeviceClass.SMOKE,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RFLinkConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the RFLink binary sensor platform."""
    gateway = entry.runtime_data
    async_add_entities([RFLinkConnectionSensor(gateway)])

    @callback
    def _build_configured(
        gateway: RFLinkGateway, subentry: ConfigSubentry
    ) -> list[BinarySensorEntity]:
        return [RFLinkBinarySensor(gateway, subentry)]

    @callback
    def _build_field_sensors(
        gateway: RFLinkGateway, subentry: ConfigSubentry
    ) -> list[BinarySensorEntity]:
        manager = _BinarySensorManager(entry, gateway, subentry, async_add_entities)
        return manager.async_setup()

    gateway.async_register_platform(
        SUBENTRY_TYPE_BINARY_SENSOR, async_add_entities, _build_configured
    )
    gateway.async_register_platform(
        SUBENTRY_TYPE_SENSOR, async_add_entities, _build_field_sensors
    )


class _BinarySensorManager:
    """Create binary sensors for boolean fields of a sensor device."""

    def __init__(
        self,
        entry: RFLinkConfigEntry,
        gateway: RFLinkGateway,
        subentry: ConfigSubentry,
        async_add_entities: AddConfigEntryEntitiesCallback,
    ) -> None:
        self._entry = entry
        self._gateway = gateway
        self._subentry = subentry
        self._async_add_entities = async_add_entities
        self._known: set[str] = set()

    @callback
    def async_setup(self) -> list[BinarySensorEntity]:
        """Return the initial entities and watch for new boolean fields."""
        device_ids = async_subentry_device_ids(self._subentry)
        entities: list[BinarySensorEntity] = []
        for device_id in device_ids:
            if packet := self._gateway.last_packet.get(device_id):
                entities.extend(self._async_entities_for(packet))

        for device_id in device_ids:
            self._entry.async_on_unload(
                async_dispatcher_connect(
                    self._gateway.hass,
                    SIGNAL_DEVICE_UPDATE.format(self._entry.entry_id, device_id),
                    self._async_packet_received,
                )
            )
        return entities

    @callback
    def _async_entities_for(self, packet: RFLinkPacket) -> list[BinarySensorEntity]:
        entities: list[BinarySensorEntity] = []
        for rflink_key in packet.sensor_keys:
            description = BINARY_SENSOR_TYPES.get(rflink_key)
            if description is None or description.key in self._known:
                continue
            self._known.add(description.key)
            entities.append(
                RFLinkFieldBinarySensor(
                    self._gateway, self._subentry, description, packet
                )
            )
        return entities

    @callback
    def _async_packet_received(self, packet: RFLinkPacket) -> None:
        if new_entities := self._async_entities_for(packet):
            self._async_add_entities(
                new_entities, config_subentry_id=self._subentry.subentry_id
            )


class RFLinkConnectionSensor(BinarySensorEntity):
    """Connectivity of the gateway itself."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_translation_key = "connection"

    def __init__(self, gateway: RFLinkGateway) -> None:
        """Initialize the connection sensor."""
        self._gateway = gateway
        self._attr_unique_id = f"rflink_connection_{gateway.entry.data[CONF_PORT]}"
        self._attr_is_on = gateway.is_connected
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, gateway.entry.entry_id)},
            name=gateway.entry.title,
            manufacturer="RFLink",
            model="Gateway",
            serial_number=gateway.port,
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to connection updates."""
        await super().async_added_to_hass()
        self._attr_is_on = self._gateway.is_connected
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_CONNECTION.format(self._gateway.entry.entry_id),
                self._async_handle_connection,
            )
        )

    @callback
    def _async_handle_connection(self, connected: bool) -> None:
        self._attr_is_on = connected
        self.async_write_ha_state()


class RFLinkBinarySensorBase(RFLinkEntity, BinarySensorEntity, RestoreEntity):
    """Shared behaviour for RFLink binary sensors."""

    def __init__(
        self,
        gateway: RFLinkGateway,
        subentry: ConfigSubentry,
        initial_packet: RFLinkPacket | None = None,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(gateway, subentry, initial_packet)
        self._off_delay: int | None = subentry.data.get(CONF_OFF_DELAY)
        self._delay_listener = None

    async def async_added_to_hass(self) -> None:
        """Restore the previous state."""
        await super().async_added_to_hass()
        if (state := await self.async_get_last_state()) is not None:
            self._attr_is_on = state.state == STATE_ON

    async def async_will_remove_from_hass(self) -> None:
        """Cancel a pending off delay."""
        if self._delay_listener is not None:
            self._delay_listener()
            self._delay_listener = None
        await super().async_will_remove_from_hass()

    @callback
    def _async_schedule_off(self) -> None:
        """Turn the sensor off again after the configured delay."""
        if not self._off_delay:
            return
        if self._delay_listener is not None:
            self._delay_listener()

        @callback
        def _off(_now) -> None:
            self._delay_listener = None
            self._attr_is_on = False
            self.async_write_ha_state()

        self._delay_listener = async_call_later(self.hass, self._off_delay, _off)


class RFLinkBinarySensor(RFLinkBinarySensorBase):
    """A binary sensor driven by RFLink switch commands."""

    _attr_name = None

    def __init__(self, gateway: RFLinkGateway, subentry: ConfigSubentry) -> None:
        """Initialize the binary sensor."""
        super().__init__(gateway, subentry)
        self._attr_unique_id = f"rflink_binary_sensor_{self._device_id}"
        self._attr_is_on = False
        if device_class := subentry.data.get(CONF_DEVICE_CLASS):
            self._attr_device_class = BinarySensorDeviceClass(device_class)

    @callback
    def async_handle_packet(self, packet: RFLinkPacket) -> None:
        """Update the state from a command packet."""
        command = packet.command
        if command in COMMANDS_ON:
            self._attr_is_on = True
        elif command in COMMANDS_OFF:
            self._attr_is_on = False
        else:
            return

        self._attr_available = True
        if self._attr_is_on:
            self._async_schedule_off()
        self.async_write_ha_state()


class RFLinkFieldBinarySensor(RFLinkBinarySensorBase):
    """A binary sensor driven by a boolean field of a sensor packet."""

    has_switch_component = False
    entity_description: RFLinkBinarySensorEntityDescription

    def __init__(
        self,
        gateway: RFLinkGateway,
        subentry: ConfigSubentry,
        description: RFLinkBinarySensorEntityDescription,
        initial_packet: RFLinkPacket | None = None,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(gateway, subentry, initial_packet)
        self.entity_description = description
        self._attr_translation_key = description.key
        self._attr_unique_id = (
            f"rflink_binary_sensor_{description.key}_{self._device_id}"
        )
        self._attr_is_on = False

    @callback
    def async_handle_packet(self, packet: RFLinkPacket) -> None:
        """Update the state from a payload field."""
        raw = packet.fields.get(self.entity_description.rflink_key)
        if raw is None:
            return

        self._attr_is_on = raw.upper() in COMMANDS_ON
        self._attr_available = True
        if self._attr_is_on:
            self._async_schedule_off()
        self.async_write_ha_state()
