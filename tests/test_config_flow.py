"""Tests for the config, options and subentry flows."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_NAME, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.usb import UsbServiceInfo
import serial

from custom_components.rflink_ui.const import (
    CONF_AUTOMATIC_ADD,
    CONF_KEEPALIVE,
    CONF_SIGNAL_REPETITIONS,
    DOMAIN,
    MANUAL_PORT,
    SUBENTRY_TYPE_SENSOR,
    SUBENTRY_TYPE_SWITCH,
)

from .conftest import TEST_PORT, feed, make_entry, setup_entry, subentry

USB_INFO = UsbServiceInfo(
    device="/dev/ttyUSB0",
    vid="2341",
    pid="0042",
    serial_number="85430353031351B03181",
    manufacturer="Arduino",
    description="Arduino Mega 2560",
)


async def test_user_flow(hass: HomeAssistant, mock_serial) -> None:
    """A gateway can be set up from a detected port."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PORT: TEST_PORT}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_PORT: TEST_PORT}
    assert result["result"].unique_id == TEST_PORT


async def test_user_flow_manual_port(hass: HomeAssistant, mock_serial) -> None:
    """A ser2net URL can be entered by hand."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PORT: MANUAL_PORT}
    )
    assert result["step_id"] == "manual_port"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PORT: "socket://192.168.1.50:2001"}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_PORT: "socket://192.168.1.50:2001"}


async def test_user_flow_cannot_connect(hass: HomeAssistant, mock_serial) -> None:
    """A port that cannot be opened shows an error."""
    with patch("serial.serial_for_url", side_effect=serial.SerialException):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_PORT: TEST_PORT}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_duplicate_port_aborts(hass: HomeAssistant, mock_serial) -> None:
    """The same port cannot be set up twice."""
    entry = make_entry()
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PORT: TEST_PORT}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_usb_discovery(hass: HomeAssistant, mock_serial) -> None:
    """A gateway plugged into USB starts a confirmation flow."""
    with patch(
        "custom_components.rflink_ui.config_flow._serial_by_id",
        return_value="/dev/serial/by-id/usb-arduino",
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USB}, data=USB_INFO
        )
        assert result["step_id"] == "usb_confirm"

        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_PORT: "/dev/serial/by-id/usb-arduino"}


async def test_reconfigure(hass: HomeAssistant, mock_serial) -> None:
    """The port of an existing gateway can be changed."""
    entry = make_entry()
    await setup_entry(hass, entry)

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PORT: TEST_PORT}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_PORT] == TEST_PORT


async def test_options_flow(hass: HomeAssistant, mock_serial) -> None:
    """Gateway wide options can be changed."""
    entry = make_entry()
    await setup_entry(hass, entry)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_AUTOMATIC_ADD: True,
            CONF_SIGNAL_REPETITIONS: 2,
            CONF_KEEPALIVE: 60,
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_AUTOMATIC_ADD] is True


async def test_add_switch_subentry(hass: HomeAssistant, mock_serial) -> None:
    """A switch can be added from the discovered device list."""
    entry = make_entry()
    await setup_entry(hass, entry)

    feed(hass, entry, "20;06;NewKaku;ID=008cbc9b;SWITCH=1;CMD=ON;")
    await hass.async_block_till_done()

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_TYPE_SWITCH), context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {"device_id": "NewKaku_008cbc9b_1", CONF_NAME: "Living room"},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert hass.states.get("switch.living_room") is not None


async def test_reconfigure_subentry_adds_alias(
    hass: HomeAssistant, mock_serial
) -> None:
    """An alias can be added to an existing sensor."""
    entry = make_entry([subentry(SUBENTRY_TYPE_SENSOR, "Xiron_4b02", "Bedroom")])
    await setup_entry(hass, entry)

    subentry_id = next(iter(entry.subentries))
    result = await entry.start_subentry_reconfigure_flow(hass, subentry_id)

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "device_id": "Xiron_4b02",
            CONF_NAME: "Bedroom",
            "force_update": False,
            "aliases": ["Tunex_4b02"],
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert entry.subentries[subentry_id].data["aliases"] == ["Tunex_4b02"]
