"""Tests for the binary sensor platform."""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.rflink_ui.const import (
    SUBENTRY_TYPE_BINARY_SENSOR,
    SUBENTRY_TYPE_SENSOR,
)

from .conftest import feed, make_entry, setup_entry, subentry


async def test_connection_sensor(hass: HomeAssistant, mock_serial) -> None:
    """The gateway exposes its connection state."""
    entry = make_entry()
    await setup_entry(hass, entry)

    state = hass.states.get("binary_sensor.rflink_dev_ttyusb_test_connection_status")
    assert state is not None
    assert state.state == STATE_ON


async def test_command_binary_sensor(hass: HomeAssistant, mock_serial) -> None:
    """A door contact follows ON and OFF commands."""
    entry = make_entry(
        [
            subentry(
                SUBENTRY_TYPE_BINARY_SENSOR,
                "Kaku_41_1",
                "Front door",
                device_class="door",
            )
        ]
    )
    await setup_entry(hass, entry)

    assert hass.states.get("binary_sensor.front_door").state == STATE_OFF

    feed(hass, entry, "20;01;Kaku;ID=41;SWITCH=1;CMD=ON;")
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.front_door").state == STATE_ON
    assert (
        hass.states.get("binary_sensor.front_door").attributes["device_class"] == "door"
    )


async def test_off_delay(
    hass: HomeAssistant, mock_serial, freezer: FrozenDateTimeFactory
) -> None:
    """A trigger only sensor switches itself off again."""
    entry = make_entry(
        [
            subentry(
                SUBENTRY_TYPE_BINARY_SENSOR,
                "Kaku_41_1",
                "Hallway motion",
                device_class="motion",
                off_delay=30,
            )
        ]
    )
    await setup_entry(hass, entry)

    feed(hass, entry, "20;01;Kaku;ID=41;SWITCH=1;CMD=ON;")
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.hallway_motion").state == STATE_ON

    freezer.tick(timedelta(seconds=31))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get("binary_sensor.hallway_motion").state == STATE_OFF


async def test_boolean_field_becomes_binary_sensor(
    hass: HomeAssistant, mock_serial
) -> None:
    """A PIR field on a sensor device gets its own binary sensor."""
    entry = make_entry([subentry(SUBENTRY_TYPE_SENSOR, "SmokeSensor_12", "Kitchen")])
    await setup_entry(hass, entry)

    feed(hass, entry, "20;01;SmokeSensor;ID=12;SMOKEALERT=ON;")
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.kitchen_smoke")
    assert state is not None
    assert state.state == STATE_ON
