"""Tests for setup, unload and migration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.rflink_ui.const import (
    CONF_AUTOMATIC_ADD,
    DOMAIN,
    SUBENTRY_TYPE_SENSOR,
    SUBENTRY_TYPE_SWITCH,
)

from .conftest import TEST_PORT, feed, make_entry, setup_entry, subentry


async def test_setup_and_unload(hass: HomeAssistant, mock_serial) -> None:
    """The entry sets up, connects and unloads cleanly."""
    entry = make_entry(
        [subentry(SUBENTRY_TYPE_SWITCH, "Unitec_1a4a_4", "Living room switch")]
    )
    await setup_entry(hass, entry)

    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.is_connected
    assert hass.states.get("switch.living_room_switch") is not None

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_gateway_device_is_created(hass: HomeAssistant, mock_serial) -> None:
    """The gateway itself shows up as a device."""
    entry = make_entry()
    await setup_entry(hass, entry)

    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    assert device is not None
    assert device.serial_number == TEST_PORT


async def test_automatic_add_creates_subentry(hass: HomeAssistant, mock_serial) -> None:
    """An unknown device becomes a subentry when automatic add is on."""
    entry = make_entry(options={CONF_AUTOMATIC_ADD: True})
    await setup_entry(hass, entry)

    feed(hass, entry, "20;3A;Oregon TempHygro;ID=0A4C;TEMP=00ba;HUM=40;BAT=OK;")
    await hass.async_block_till_done()

    subentries = list(entry.subentries.values())
    assert len(subentries) == 1
    assert subentries[0].subentry_type == SUBENTRY_TYPE_SENSOR
    assert subentries[0].data["device_id"] == "Oregon TempHygro_0A4C"
    assert hass.states.get("sensor.oregon_temphygro_0a4c_temperature") is not None


async def test_discovery_buffer_without_automatic_add(
    hass: HomeAssistant, mock_serial
) -> None:
    """Unknown devices are only buffered when automatic add is off."""
    entry = make_entry()
    await setup_entry(hass, entry)

    feed(hass, entry, "20;06;NewKaku;ID=008cbc9b;SWITCH=1;CMD=ON;")
    await hass.async_block_till_done()

    assert not entry.subentries
    assert "NewKaku_008cbc9b_1" in entry.runtime_data.discovered


async def test_migration_from_version_1(hass: HomeAssistant, mock_serial) -> None:
    """Legacy options are converted into subentries."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_PORT: TEST_PORT},
        options={
            "switches": {"Unitec_1a4a_4": "Living room switch"},
            "sensors": {"Oregon TempHygro_0A4C": "Garden"},
            "lights": {"NewKaku_1_1": {"name": "Hall light", "type": "hybrid"}},
            "binary_sensors": {
                "Kaku_42_1": {
                    "name": "Front door",
                    "device_class": "door",
                    "off_delay": 5,
                }
            },
        },
        version=1,
    )
    await setup_entry(hass, entry)

    assert entry.version == 2
    assert entry.unique_id == TEST_PORT
    assert "switches" not in entry.options

    by_device = {sub.data["device_id"]: sub for sub in entry.subentries.values()}
    assert by_device["Unitec_1a4a_4"].subentry_type == SUBENTRY_TYPE_SWITCH
    assert by_device["NewKaku_1_1"].data["light_type"] == "hybrid"
    assert by_device["Kaku_42_1"].data["off_delay"] == 5
    assert by_device["Oregon TempHygro_0A4C"].subentry_type == SUBENTRY_TYPE_SENSOR

    assert hass.states.get("switch.living_room_switch") is not None
    assert hass.states.get("light.hall_light") is not None
    assert hass.states.get("binary_sensor.front_door") is not None


async def test_migration_keeps_existing_entities(
    hass: HomeAssistant, mock_serial
) -> None:
    """Entities registered before the migration keep their entity id."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_PORT: TEST_PORT},
        options={"switches": {"Unitec_1a4a_4": "Living room switch"}},
        version=1,
    )
    entry.add_to_hass(hass)

    registry = er.async_get(hass)
    existing = registry.async_get_or_create(
        "switch",
        DOMAIN,
        "rflink_switch_Unitec_1a4a_4",
        suggested_object_id="old_name",
        config_entry=entry,
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(existing.entity_id) is not None
