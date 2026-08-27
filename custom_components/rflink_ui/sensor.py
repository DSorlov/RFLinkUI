"""Sensor platform for RFLink UI.

Every measurement in an RFLink packet becomes its own entity instead of an
attribute, and entities appear automatically as new fields are received.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigSubentry
from homeassistant.const import (
    DEGREE,
    LIGHT_LUX,
    PERCENTAGE,
    UV_INDEX,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfLength,
    UnitOfPower,
    UnitOfPrecipitationDepth,
    UnitOfPressure,
    UnitOfRatio,
    UnitOfSoundPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfVolumetricFlux,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import CONF_FORCE_UPDATE, SIGNAL_DEVICE_UPDATE, SUBENTRY_TYPE_SENSOR
from .entity import RFLinkEntity
from .gateway import RFLinkConfigEntry, RFLinkGateway, async_subentry_device_ids
from .protocol import RFLinkPacket, convert_value

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class RFLinkSensorEntityDescription(SensorEntityDescription):
    """Describes an RFLink sensor, keyed by its RFLink payload field."""

    rflink_key: str


def _description(
    rflink_key: str, key: str, **kwargs: object
) -> RFLinkSensorEntityDescription:
    return RFLinkSensorEntityDescription(
        rflink_key=rflink_key, key=key, translation_key=key, **kwargs
    )


#: Maps an RFLink payload field onto the entity it should create.
SENSOR_TYPES: dict[str, RFLinkSensorEntityDescription] = {
    description.rflink_key: description
    for description in (
        _description(
            "TEMP",
            "temperature",
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ),
        _description(
            "HUM",
            "humidity",
            device_class=SensorDeviceClass.HUMIDITY,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=PERCENTAGE,
        ),
        _description(
            "BARO",
            "barometric_pressure",
            device_class=SensorDeviceClass.ATMOSPHERIC_PRESSURE,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfPressure.HPA,
        ),
        _description(
            "HSTATUS",
            "humidity_status",
            device_class=SensorDeviceClass.ENUM,
            options=["normal", "comfortable", "dry", "wet", "unknown"],
        ),
        _description(
            "BFORECAST",
            "weather_forecast",
            device_class=SensorDeviceClass.ENUM,
            options=[
                "no_info",
                "sunny",
                "partly_cloudy",
                "cloudy",
                "rain",
                "unknown",
            ],
        ),
        _description(
            "UV",
            "uv_intensity",
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UV_INDEX,
        ),
        _description(
            "LUX",
            "light_intensity",
            device_class=SensorDeviceClass.ILLUMINANCE,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=LIGHT_LUX,
        ),
        _description(
            "BAT",
            "battery",
            device_class=SensorDeviceClass.ENUM,
            options=["ok", "low"],
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
        _description(
            "RAIN",
            "total_rain",
            device_class=SensorDeviceClass.PRECIPITATION,
            state_class=SensorStateClass.TOTAL_INCREASING,
            native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        ),
        _description(
            "RAINTOT",
            "total_rain",
            device_class=SensorDeviceClass.PRECIPITATION,
            state_class=SensorStateClass.TOTAL_INCREASING,
            native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        ),
        _description(
            "RAINRATE",
            "rain_rate",
            device_class=SensorDeviceClass.PRECIPITATION_INTENSITY,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfVolumetricFlux.MILLIMETERS_PER_HOUR,
        ),
        _description(
            "WINSP",
            "windspeed",
            device_class=SensorDeviceClass.WIND_SPEED,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        ),
        _description(
            "AWINSP",
            "average_windspeed",
            device_class=SensorDeviceClass.WIND_SPEED,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        ),
        _description(
            "WINGS",
            "windgusts",
            device_class=SensorDeviceClass.WIND_SPEED,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        ),
        _description(
            "WINDIR",
            "winddirection",
            device_class=SensorDeviceClass.WIND_DIRECTION,
            state_class=SensorStateClass.MEASUREMENT_ANGLE,
            native_unit_of_measurement=DEGREE,
        ),
        _description(
            "WINCHL",
            "windchill",
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ),
        _description(
            "WINTMP",
            "windtemp",
            device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ),
        _description(
            "CO2",
            "co2_air_quality",
            device_class=SensorDeviceClass.CO2,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfRatio.PARTS_PER_MILLION,
        ),
        _description(
            "SOUND",
            "noise_level",
            device_class=SensorDeviceClass.SOUND_PRESSURE,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfSoundPressure.DECIBEL,
        ),
        _description(
            "WATT",
            "watt",
            device_class=SensorDeviceClass.POWER,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfPower.WATT,
        ),
        _description(
            "KWATT",
            "kilowatt",
            device_class=SensorDeviceClass.POWER,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfPower.KILO_WATT,
        ),
        _description(
            "CURRENT",
            "current_phase_1",
            device_class=SensorDeviceClass.CURRENT,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        ),
        _description(
            "CURRENT2",
            "current_phase_2",
            device_class=SensorDeviceClass.CURRENT,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        ),
        _description(
            "CURRENT3",
            "current_phase_3",
            device_class=SensorDeviceClass.CURRENT,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        ),
        _description(
            "VOLT",
            "voltage",
            device_class=SensorDeviceClass.VOLTAGE,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        ),
        _description(
            "DIST",
            "distance",
            device_class=SensorDeviceClass.DISTANCE,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfLength.CENTIMETERS,
        ),
        _description(
            "METER",
            "meter_value",
            state_class=SensorStateClass.TOTAL_INCREASING,
        ),
        _description(
            "CHIME",
            "doorbell_melody",
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
    )
}

LAST_SEEN_DESCRIPTION = RFLinkSensorEntityDescription(
    rflink_key="",
    key="last_seen",
    translation_key="last_seen",
    device_class=SensorDeviceClass.TIMESTAMP,
    entity_category=EntityCategory.DIAGNOSTIC,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RFLinkConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the RFLink sensor platform."""
    gateway = entry.runtime_data

    @callback
    def _build(gateway: RFLinkGateway, subentry: ConfigSubentry) -> list[SensorEntity]:
        manager = _SensorManager(entry, gateway, subentry, async_add_entities)
        return manager.async_setup()

    gateway.async_register_platform(SUBENTRY_TYPE_SENSOR, async_add_entities, _build)


class _SensorManager:
    """Create sensor entities for a device as new fields show up."""

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
    def async_setup(self) -> list[SensorEntity]:
        """Return the initial entities and start watching for new fields."""
        entities: list[SensorEntity] = [
            RFLinkLastSeenSensor(self._gateway, self._subentry)
        ]
        for packet in self._known_packets():
            entities.extend(self._async_entities_for(packet))

        entry_id = self._entry.entry_id
        for device_id in self._device_ids():
            self._entry.async_on_unload(
                async_dispatcher_connect(
                    self._gateway.hass,
                    SIGNAL_DEVICE_UPDATE.format(entry_id, device_id),
                    self._async_packet_received,
                )
            )
        return entities

    def _device_ids(self) -> list[str]:
        return async_subentry_device_ids(self._subentry)

    def _known_packets(self) -> list[RFLinkPacket]:
        """Return the most recent packet seen for this device."""
        return [
            packet
            for device_id in self._device_ids()
            if (packet := self._gateway.last_packet.get(device_id)) is not None
        ]

    @callback
    def _async_entities_for(self, packet: RFLinkPacket) -> list[SensorEntity]:
        entities: list[SensorEntity] = []
        for rflink_key in packet.sensor_keys:
            description = SENSOR_TYPES.get(rflink_key)
            if description is None or description.key in self._known:
                continue
            self._known.add(description.key)
            entities.append(
                RFLinkSensor(self._gateway, self._subentry, description, packet)
            )
        return entities

    @callback
    def _async_packet_received(self, packet: RFLinkPacket) -> None:
        """Add entities for measurements that were not seen before."""
        if new_entities := self._async_entities_for(packet):
            _LOGGER.debug(
                "Adding %s new sensor entities for %s",
                len(new_entities),
                self._subentry.title,
            )
            self._async_add_entities(
                new_entities, config_subentry_id=self._subentry.subentry_id
            )


class RFLinkSensorBase(RFLinkEntity, SensorEntity):
    """Common bits for RFLink sensors."""

    has_switch_component = False
    entity_description: RFLinkSensorEntityDescription

    def __init__(
        self,
        gateway: RFLinkGateway,
        subentry: ConfigSubentry,
        description: RFLinkSensorEntityDescription,
        initial_packet: RFLinkPacket | None = None,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(gateway, subentry, initial_packet)
        self.entity_description = description
        self._attr_unique_id = f"rflink_sensor_{description.key}_{self._device_id}"
        self._attr_force_update = subentry.data.get(CONF_FORCE_UPDATE, False)


class RFLinkSensor(RFLinkSensorBase, RestoreSensor):
    """A single measurement reported by an RFLink device."""

    async def async_added_to_hass(self) -> None:
        """Restore the previous value."""
        await super().async_added_to_hass()
        if (last_data := await self.async_get_last_sensor_data()) is not None:
            self._attr_native_value = last_data.native_value

    @callback
    def async_handle_packet(self, packet: RFLinkPacket) -> None:
        """Update the value from a received packet."""
        raw = packet.fields.get(self.entity_description.rflink_key)
        if raw is None:
            return

        value = convert_value(self.entity_description.rflink_key, raw)
        if self.entity_description.device_class is SensorDeviceClass.ENUM:
            value = str(value).lower()
            if value not in (self.entity_description.options or []):
                value = "unknown"

        self._attr_native_value = value
        self._attr_available = True
        self.async_write_ha_state()


class RFLinkLastSeenSensor(RFLinkSensorBase):
    """Timestamp of the last packet received from a device."""

    def __init__(self, gateway: RFLinkGateway, subentry: ConfigSubentry) -> None:
        """Initialize the sensor."""
        super().__init__(gateway, subentry, LAST_SEEN_DESCRIPTION)
        self._attr_force_update = False

    @property
    def native_value(self) -> datetime | None:
        """Return when this device was last heard from."""
        for device_id in (self._device_id, *self._aliases):
            if timestamp := self.gateway.last_seen.get(device_id):
                return timestamp
        return None

    @callback
    def async_handle_packet(self, packet: RFLinkPacket) -> None:
        """Refresh the timestamp."""
        self.gateway.last_seen[self._device_id] = dt_util.utcnow()
        self._attr_available = True
        self.async_write_ha_state()
