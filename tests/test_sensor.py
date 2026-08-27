"""Tests for the sensor platform."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from custom_components.rflink_ui.const import SUBENTRY_TYPE_SENSOR

from .conftest import feed, make_entry, setup_entry, subentry

WEATHER_PACKET = (
    "20;12;Alecto V1;ID=0334;TEMP=00ba;HUM=55;BARO=03e8;"
    "WINSP=0032;WINDIR=4;RAIN=0010;BAT=OK;"
)


async def test_measurements_become_separate_entities(
    hass: HomeAssistant, mock_serial
) -> None:
    """Every field in the packet gets its own entity, not an attribute."""
    entry = make_entry(
        [subentry(SUBENTRY_TYPE_SENSOR, "Alecto V1_0334", "Weather station")]
    )
    await setup_entry(hass, entry)

    feed(hass, entry, WEATHER_PACKET)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.weather_station_temperature").state == "18.6"
    assert hass.states.get("sensor.weather_station_humidity").state == "55"
    assert hass.states.get("sensor.weather_station_barometric_pressure").state == "1000"
    assert hass.states.get("sensor.weather_station_wind_speed").state == "5.0"
    assert hass.states.get("sensor.weather_station_wind_direction").state == "90.0"
    assert hass.states.get("sensor.weather_station_total_rain").state == "1.6"
    assert hass.states.get("sensor.weather_station_battery_status").state == "ok"

    temperature = hass.states.get("sensor.weather_station_temperature")
    assert "humidity" not in temperature.attributes
    assert temperature.attributes["unit_of_measurement"] == "°C"


async def test_new_field_creates_entity_later(hass: HomeAssistant, mock_serial) -> None:
    """A measurement that only appears later still gets an entity."""
    entry = make_entry([subentry(SUBENTRY_TYPE_SENSOR, "Xiron_2203", "Bedroom")])
    await setup_entry(hass, entry)

    feed(hass, entry, "20;01;Xiron;ID=2203;TEMP=00dc;")
    await hass.async_block_till_done()
    assert hass.states.get("sensor.bedroom_humidity") is None

    feed(hass, entry, "20;02;Xiron;ID=2203;TEMP=00dc;HUM=50;")
    await hass.async_block_till_done()
    assert hass.states.get("sensor.bedroom_humidity").state == "50"


async def test_aliases_feed_the_same_device(hass: HomeAssistant, mock_serial) -> None:
    """A second protocol id updates the same entities."""
    entry = make_entry(
        [
            subentry(
                SUBENTRY_TYPE_SENSOR,
                "Xiron_4b02",
                "Bedroom",
                aliases=["Tunex_4b02"],
            )
        ]
    )
    await setup_entry(hass, entry)

    feed(hass, entry, "20;01;Tunex;ID=4b02;TEMP=00c8;")
    await hass.async_block_till_done()

    assert hass.states.get("sensor.bedroom_temperature").state == "20.0"


async def test_last_seen_sensor(hass: HomeAssistant, mock_serial) -> None:
    """A diagnostic timestamp tracks when the device was last heard."""
    entry = make_entry([subentry(SUBENTRY_TYPE_SENSOR, "Xiron_2203", "Bedroom")])
    await setup_entry(hass, entry)

    assert hass.states.get("sensor.bedroom_last_seen").state == "unknown"

    feed(hass, entry, "20;01;Xiron;ID=2203;TEMP=00dc;")
    await hass.async_block_till_done()

    assert hass.states.get("sensor.bedroom_last_seen").state != "unknown"


async def test_f007_th_channel_device(hass: HomeAssistant, mock_serial) -> None:
    """An F007_TH sensor is addressed by its stable channel."""
    entry = make_entry([subentry(SUBENTRY_TYPE_SENSOR, "F007_TH_CH7", "Shed")])
    await setup_entry(hass, entry)

    feed(hass, entry, "20;01;F007_TH;ID=45246;TEMP=00ba;HUM=40;")
    await hass.async_block_till_done()

    assert hass.states.get("sensor.shed_temperature").state == "18.6"


async def test_force_update_option(hass: HomeAssistant, mock_serial) -> None:
    """With force update on, an identical reading still bumps last_updated."""
    entry = make_entry(
        [subentry(SUBENTRY_TYPE_SENSOR, "Xiron_2203", "Bedroom", force_update=True)]
    )
    await setup_entry(hass, entry)

    feed(hass, entry, "20;01;Xiron;ID=2203;TEMP=00dc;")
    await hass.async_block_till_done()
    first = hass.states.get("sensor.bedroom_temperature")

    feed(hass, entry, "20;02;Xiron;ID=2203;TEMP=00dc;")
    await hass.async_block_till_done()
    second = hass.states.get("sensor.bedroom_temperature")

    assert first.state == second.state
    assert second.last_updated > first.last_updated
