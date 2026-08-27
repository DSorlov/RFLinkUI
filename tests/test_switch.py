"""Tests for the switch platform."""

from __future__ import annotations

from homeassistant.const import ATTR_ENTITY_ID, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant

from custom_components.rflink_ui.const import SUBENTRY_TYPE_SWITCH

from .conftest import feed, make_entry, setup_entry, subentry

DEVICE_ID = "NewKaku_008cbc9b_1"
ENTITY_ID = "switch.living_room"


async def test_state_follows_remote(hass: HomeAssistant, mock_serial) -> None:
    """Commands from a physical remote update the switch."""
    entry = make_entry([subentry(SUBENTRY_TYPE_SWITCH, DEVICE_ID, "Living room")])
    await setup_entry(hass, entry)

    assert hass.states.get(ENTITY_ID).state == STATE_OFF

    feed(hass, entry, "20;06;NewKaku;ID=008cbc9b;SWITCH=1;CMD=ON;")
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == STATE_ON

    feed(hass, entry, "20;07;NewKaku;ID=008cbc9b;SWITCH=1;CMD=OFF;")
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == STATE_OFF


async def test_repeated_command_updates_timestamp(
    hass: HomeAssistant, mock_serial
) -> None:
    """A repeated identical command still fires a state change."""
    entry = make_entry([subentry(SUBENTRY_TYPE_SWITCH, DEVICE_ID, "Living room")])
    await setup_entry(hass, entry)

    feed(hass, entry, "20;06;NewKaku;ID=008cbc9b;SWITCH=1;CMD=OFF;")
    await hass.async_block_till_done()
    first = hass.states.get(ENTITY_ID)

    feed(hass, entry, "20;07;NewKaku;ID=008cbc9b;SWITCH=1;CMD=OFF;")
    await hass.async_block_till_done()
    second = hass.states.get(ENTITY_ID)

    assert second.last_updated > first.last_updated


async def test_group_command_switches_off(hass: HomeAssistant, mock_serial) -> None:
    """An ALLOFF from the remote turns off every button of that address."""
    entry = make_entry([subentry(SUBENTRY_TYPE_SWITCH, DEVICE_ID, "Living room")])
    await setup_entry(hass, entry)

    feed(hass, entry, "20;06;NewKaku;ID=008cbc9b;SWITCH=1;CMD=ON;")
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == STATE_ON

    feed(hass, entry, "20;24;NewKaku;ID=008cbc9b;SWITCH=0;CMD=ALLOFF;")
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == STATE_OFF


async def test_turn_on_sends_command(hass: HomeAssistant, mock_serial) -> None:
    """Turning the switch on writes the expected packet."""
    entry = make_entry([subentry(SUBENTRY_TYPE_SWITCH, DEVICE_ID, "Living room")])
    await setup_entry(hass, entry)

    await hass.services.async_call(
        "switch", "turn_on", {ATTR_ENTITY_ID: ENTITY_ID}, blocking=True
    )

    assert "10;NewKaku;008cbc9b;1;ON;" in mock_serial["writer"].lines
    assert hass.states.get(ENTITY_ID).state == STATE_ON


async def test_signal_repetitions(hass: HomeAssistant, mock_serial) -> None:
    """Commands are repeated as configured."""
    entry = make_entry(
        [subentry(SUBENTRY_TYPE_SWITCH, DEVICE_ID, "Living room")],
        options={"signal_repetitions": 3},
    )
    await setup_entry(hass, entry)

    await hass.services.async_call(
        "switch", "turn_off", {ATTR_ENTITY_ID: ENTITY_ID}, blocking=True
    )

    assert mock_serial["writer"].lines.count("10;NewKaku;008cbc9b;1;OFF;") == 3
