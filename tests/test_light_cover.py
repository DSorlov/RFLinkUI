"""Tests for the light and cover platforms."""

from __future__ import annotations

from homeassistant.components.light import ATTR_BRIGHTNESS
from homeassistant.const import ATTR_ENTITY_ID, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant

from custom_components.rflink_ui.const import SUBENTRY_TYPE_COVER, SUBENTRY_TYPE_LIGHT

from .conftest import feed, make_entry, setup_entry, subentry

LIGHT_ID = "light.hall"
COVER_ID = "cover.kitchen_shutter"


async def test_dimmable_light_sends_level(hass: HomeAssistant, mock_serial) -> None:
    """A dimmable light sends a numeric level."""
    entry = make_entry(
        [subentry(SUBENTRY_TYPE_LIGHT, "NewKaku_1a4a_4", "Hall", light_type="dimmable")]
    )
    await setup_entry(hass, entry)

    await hass.services.async_call(
        "light",
        "turn_on",
        {ATTR_ENTITY_ID: LIGHT_ID, ATTR_BRIGHTNESS: 128},
        blocking=True,
    )

    assert "10;NewKaku;1a4a;4;8;" in mock_serial["writer"].lines
    assert hass.states.get(LIGHT_ID).state == STATE_ON


async def test_hybrid_light_sends_level_and_on(
    hass: HomeAssistant, mock_serial
) -> None:
    """A hybrid light sends the level followed by ON."""
    entry = make_entry(
        [subentry(SUBENTRY_TYPE_LIGHT, "NewKaku_1a4a_4", "Hall", light_type="hybrid")]
    )
    await setup_entry(hass, entry)

    await hass.services.async_call(
        "light",
        "turn_on",
        {ATTR_ENTITY_ID: LIGHT_ID, ATTR_BRIGHTNESS: 255},
        blocking=True,
    )

    assert mock_serial["writer"].lines == [
        "10;NewKaku;1a4a;4;15;",
        "10;NewKaku;1a4a;4;ON;",
    ]


async def test_toggle_light_flips_state(hass: HomeAssistant, mock_serial) -> None:
    """A toggle light flips on every ON command."""
    entry = make_entry(
        [subentry(SUBENTRY_TYPE_LIGHT, "Livolo_1a4a_4", "Hall", light_type="toggle")]
    )
    await setup_entry(hass, entry)

    feed(hass, entry, "20;01;Livolo;ID=1a4a;SWITCH=4;CMD=ON;")
    await hass.async_block_till_done()
    assert hass.states.get(LIGHT_ID).state == STATE_ON

    feed(hass, entry, "20;02;Livolo;ID=1a4a;SWITCH=4;CMD=ON;")
    await hass.async_block_till_done()
    assert hass.states.get(LIGHT_ID).state == STATE_OFF


async def test_cover_open_close_stop(hass: HomeAssistant, mock_serial) -> None:
    """A cover sends UP, DOWN and STOP."""
    entry = make_entry(
        [subentry(SUBENTRY_TYPE_COVER, "Somfy_1a4a_1", "Kitchen shutter")]
    )
    await setup_entry(hass, entry)

    for service, expected in (
        ("open_cover", "10;Somfy;1a4a;1;UP;"),
        ("close_cover", "10;Somfy;1a4a;1;DOWN;"),
        ("stop_cover", "10;Somfy;1a4a;1;STOP;"),
    ):
        await hass.services.async_call(
            "cover", service, {ATTR_ENTITY_ID: COVER_ID}, blocking=True
        )
        assert expected in mock_serial["writer"].lines


async def test_inverted_cover(hass: HomeAssistant, mock_serial) -> None:
    """An inverted cover swaps UP and DOWN on the wire."""
    entry = make_entry(
        [
            subentry(
                SUBENTRY_TYPE_COVER,
                "NewKaku_1a4a_1",
                "Kitchen shutter",
                inverted=True,
            )
        ]
    )
    await setup_entry(hass, entry)

    await hass.services.async_call(
        "cover", "open_cover", {ATTR_ENTITY_ID: COVER_ID}, blocking=True
    )

    assert "10;NewKaku;1a4a;1;DOWN;" in mock_serial["writer"].lines
