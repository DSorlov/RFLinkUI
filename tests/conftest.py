"""Shared fixtures for the RFLink UI tests."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from unittest.mock import MagicMock, patch

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.const import CONF_PORT
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.rflink_ui.const import DOMAIN

TEST_PORT = "/dev/ttyUSB-test"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the custom integration for every test."""
    yield


class MockStreamReader:
    """Stream reader backed by a queue so tests can feed packets."""

    def __init__(self) -> None:
        self.queue: asyncio.Queue[bytes] = asyncio.Queue()

    async def readline(self) -> bytes:
        return await self.queue.get()

    def feed_line(self, line: str) -> None:
        """Feed a single RFLink line to the reader."""
        self.queue.put_nowait(f"{line}\n".encode())


class MockStreamWriter:
    """Stream writer that records what was written."""

    def __init__(self) -> None:
        self.written: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.written.append(data)

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        return None

    async def wait_closed(self) -> None:
        return None

    @property
    def lines(self) -> list[str]:
        """Return everything written as decoded lines."""
        return [item.decode().strip() for item in self.written]


@pytest.fixture
def mock_serial() -> Iterator[dict]:
    """Mock the serial layer used by the gateway and the config flow."""
    reader = MockStreamReader()
    writer = MockStreamWriter()

    async def _open(url: str, baudrate: int, **kwargs):
        return reader, writer

    port = MagicMock()
    port.device = TEST_PORT

    with (
        patch(
            "custom_components.rflink_ui.gateway.serial_asyncio.open_serial_connection",
            side_effect=_open,
        ) as open_mock,
        patch("serial.serial_for_url"),
        patch("serial.tools.list_ports.comports", return_value=[port]),
    ):
        yield {"reader": reader, "writer": writer, "open": open_mock}


def make_entry(
    subentries: list[ConfigSubentryData] | None = None,
    options: dict | None = None,
) -> MockConfigEntry:
    """Create a config entry for the current schema version."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=f"RFLink ({TEST_PORT})",
        data={CONF_PORT: TEST_PORT},
        options=options or {},
        unique_id=TEST_PORT,
        version=2,
        subentries_data=subentries or [],
    )


def subentry(
    subentry_type: str, device_id: str, title: str, **data
) -> ConfigSubentryData:
    """Build subentry data for a device."""
    return ConfigSubentryData(
        data={"device_id": device_id, "aliases": [], **data},
        subentry_type=subentry_type,
        title=title,
        unique_id=device_id,
    )


async def setup_entry(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Add and set up a config entry."""
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def feed(hass: HomeAssistant, entry: MockConfigEntry, packet: str) -> None:
    """Push a packet into the gateway as if it was received."""
    entry.runtime_data.async_handle_line(packet)
