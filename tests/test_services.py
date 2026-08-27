"""Tests for the integration actions."""

from __future__ import annotations

from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
import pytest

from custom_components.rflink_ui.const import (
    DOMAIN,
    SERVICE_SEND_COMMAND,
    SERVICE_SEND_RAW,
    SERVICE_SIMULATE_PACKET,
    SUBENTRY_TYPE_SWITCH,
)

from .conftest import make_entry, setup_entry, subentry

TRANSMITTER = "radio_frequency.rflink_dev_ttyusb_test_transmitter"


async def test_simulate_packet(hass: HomeAssistant, mock_serial) -> None:
    """A simulated packet drives the entities."""
    entry = make_entry(
        [subentry(SUBENTRY_TYPE_SWITCH, "NewKaku_008cbc9b_1", "Living room")]
    )
    await setup_entry(hass, entry)

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SIMULATE_PACKET,
        {"packet": "20;06;NewKaku;ID=008cbc9b;SWITCH=1;CMD=ON;"},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert hass.states.get("switch.living_room").state == "on"


async def test_send_command(hass: HomeAssistant, mock_serial) -> None:
    """A protocol command is assembled into a packet."""
    entry = make_entry()
    await setup_entry(hass, entry)

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SEND_COMMAND,
        {ATTR_ENTITY_ID: TRANSMITTER, "protocol": "Unitec", "command": "1a4a;4;ON"},
        blocking=True,
    )

    assert "10;Unitec;1a4a;4;ON;" in mock_serial["writer"].lines


async def test_send_raw(hass: HomeAssistant, mock_serial) -> None:
    """A raw packet is written verbatim, which is what GPIO needs."""
    entry = make_entry()
    await setup_entry(hass, entry)

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SEND_RAW,
        {ATTR_ENTITY_ID: TRANSMITTER, "packet": "10;GPIOset;32;0;ON;"},
        blocking=True,
    )

    assert "10;GPIOset;32;0;ON;" in mock_serial["writer"].lines


async def test_send_raw_while_disconnected(hass: HomeAssistant, mock_serial) -> None:
    """Sending while the gateway is down fails instead of writing."""
    entry = make_entry()
    await setup_entry(hass, entry)
    entry.runtime_data.is_connected = False

    with pytest.raises(ConnectionError):
        await entry.runtime_data.async_send_raw("10;PING;")

    assert "10;PING;" not in mock_serial["writer"].lines
