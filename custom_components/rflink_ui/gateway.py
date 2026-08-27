"""Serial gateway handling for the RFLink UI integration."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.const import CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util, ulid as ulid_util
import serial_asyncio_fast as serial_asyncio

from .const import (
    COMMANDS_GROUP,
    CONF_ALIASES,
    CONF_AUTOMATIC_ADD,
    CONF_DEVICE_ID,
    CONF_KEEPALIVE,
    CONF_SIGNAL_REPETITIONS,
    DEFAULT_AUTOMATIC_ADD,
    DEFAULT_BAUDRATE,
    DEFAULT_RECONNECT_INTERVAL,
    DEFAULT_SIGNAL_REPETITIONS,
    DISCOVERY_BUFFER_SIZE,
    KEEPALIVE_INTERVAL,
    MAX_RECONNECT_INTERVAL,
    SIGNAL_CONNECTION,
    SIGNAL_DEVICE_UPDATE,
    SIGNAL_GROUP_UPDATE,
    SUBENTRY_TYPE_SENSOR,
    SUBENTRY_TYPE_SWITCH,
)
from .protocol import RFLinkPacket, parse_packet

if TYPE_CHECKING:
    from homeassistant.helpers.entity import Entity

_LOGGER = logging.getLogger(__name__)

type RFLinkConfigEntry = ConfigEntry[RFLinkGateway]
type EntityBuilder = Callable[["RFLinkGateway", ConfigSubentry], list["Entity"]]


@dataclass(slots=True)
class DiscoveredDevice:
    """A device seen on the air that is not configured yet."""

    device_id: str
    device_type: str
    protocol: str
    fields: dict[str, str]
    last_seen: datetime


@dataclass(slots=True)
class _PlatformRegistration:
    add_entities: AddConfigEntryEntitiesCallback
    build_entities: EntityBuilder


class RFLinkGateway:
    """Maintain the serial link to an RFLink gateway and route its packets."""

    def __init__(self, hass: HomeAssistant, entry: RFLinkConfigEntry) -> None:
        """Initialize the gateway."""
        self.hass = hass
        self.entry = entry
        self.port: str = entry.data[CONF_PORT]
        self.is_connected = False
        self.firmware: str | None = None
        self.seen: dict[str, DiscoveredDevice] = {}
        self.last_seen: dict[str, datetime] = {}
        self.last_packet: dict[str, RFLinkPacket] = {}
        self.packets_received = 0

        self._writer: asyncio.StreamWriter | None = None
        self._connection_task: asyncio.Task[None] | None = None
        self._keepalive_task: asyncio.Task[None] | None = None
        self._platforms: dict[str, list[_PlatformRegistration]] = {}
        self._pending_subentries: dict[str, ConfigSubentry] = {}
        self._send_lock = asyncio.Lock()
        self.known_subentries: dict[str, dict[str, Any]] = {
            subentry_id: dict(subentry.data)
            for subentry_id, subentry in entry.subentries.items()
        }

    # ------------------------------------------------------------------
    # Configuration helpers
    # ------------------------------------------------------------------

    @property
    def automatic_add(self) -> bool:
        """Return whether unknown devices are added automatically."""
        return self.entry.options.get(CONF_AUTOMATIC_ADD, DEFAULT_AUTOMATIC_ADD)

    @property
    def signal_repetitions(self) -> int:
        """Return how many times each outgoing command is repeated."""
        return self.entry.options.get(
            CONF_SIGNAL_REPETITIONS, DEFAULT_SIGNAL_REPETITIONS
        )

    @property
    def keepalive_interval(self) -> int:
        """Return the keep-alive ping interval in seconds."""
        return self.entry.options.get(CONF_KEEPALIVE, KEEPALIVE_INTERVAL)

    @callback
    def async_configured_device_ids(self) -> set[str]:
        """Return every device id and alias currently configured."""
        configured: set[str] = set()
        for subentry in self.entry.subentries.values():
            if device_id := subentry.data.get(CONF_DEVICE_ID):
                configured.add(device_id)
            configured.update(subentry.data.get(CONF_ALIASES, []))
        return configured

    @property
    def discovered(self) -> dict[str, DiscoveredDevice]:
        """Return the devices seen on the air that are not configured yet."""
        configured = self.async_configured_device_ids()
        return {
            device_id: device
            for device_id, device in self.seen.items()
            if device_id not in configured
        }

    # ------------------------------------------------------------------
    # Platform registration
    # ------------------------------------------------------------------

    @callback
    def async_register_platform(
        self,
        subentry_type: str,
        add_entities: AddConfigEntryEntitiesCallback,
        build_entities: EntityBuilder,
    ) -> None:
        """Register a platform so subentries can be set up dynamically."""
        self._platforms.setdefault(subentry_type, []).append(
            _PlatformRegistration(add_entities, build_entities)
        )
        for subentry_id, subentry in list(self._pending_subentries.items()):
            if subentry.subentry_type == subentry_type:
                del self._pending_subentries[subentry_id]
                self.async_add_subentry_entities(subentry)

    @callback
    def async_add_subentry_entities(self, subentry: ConfigSubentry) -> None:
        """Create the entities belonging to a subentry."""
        registrations = self._platforms.get(subentry.subentry_type)
        if not registrations:
            # The platform has not finished setting up yet, retry on register.
            self._pending_subentries[subentry.subentry_id] = subentry
            return
        for registration in registrations:
            if entities := registration.build_entities(self, subentry):
                registration.add_entities(
                    entities, config_subentry_id=subentry.subentry_id
                )

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    @callback
    def async_start(self) -> None:
        """Start maintaining the serial connection."""
        self._connection_task = self.entry.async_create_background_task(
            self.hass, self._async_connection_loop(), f"{self.port} connection"
        )

    async def async_stop(self) -> None:
        """Tear down the serial connection."""
        for task in (self._connection_task, self._keepalive_task):
            if task is not None:
                task.cancel()
        self._connection_task = None
        self._keepalive_task = None
        await self._async_close_writer()
        self.is_connected = False

    async def _async_close_writer(self) -> None:
        if self._writer is None:
            return
        writer, self._writer = self._writer, None
        try:
            writer.close()
            await writer.wait_closed()
        except (TimeoutError, OSError, ConnectionError) as err:
            _LOGGER.debug("Error while closing connection to %s: %s", self.port, err)

    async def _async_connection_loop(self) -> None:
        """Connect, read and reconnect with exponential backoff."""
        delay = DEFAULT_RECONNECT_INTERVAL
        logged_failure = False

        while True:
            try:
                reader, writer = await serial_asyncio.open_serial_connection(
                    url=self.port, baudrate=DEFAULT_BAUDRATE
                )
            except (OSError, ValueError) as err:
                if not logged_failure:
                    _LOGGER.error(
                        "Could not connect to RFLink on %s: %s", self.port, err
                    )
                    logged_failure = True
                else:
                    _LOGGER.debug("Reconnect to %s failed: %s", self.port, err)
                await asyncio.sleep(delay)
                delay = min(delay * 2, MAX_RECONNECT_INTERVAL)
                continue

            _LOGGER.info("Connected to RFLink on %s", self.port)
            delay = DEFAULT_RECONNECT_INTERVAL
            logged_failure = False
            self._writer = writer
            self._set_connected(True)
            self._keepalive_task = self.entry.async_create_background_task(
                self.hass, self._async_keepalive(), f"{self.port} keepalive"
            )

            try:
                await self._async_read(reader)
            except asyncio.CancelledError:
                raise
            except Exception as err:
                _LOGGER.debug("RFLink read loop on %s ended: %s", self.port, err)

            if self._keepalive_task is not None:
                self._keepalive_task.cancel()
                self._keepalive_task = None
            self._set_connected(False)
            await self._async_close_writer()
            _LOGGER.info("RFLink connection to %s lost, reconnecting", self.port)
            await asyncio.sleep(delay)

    async def _async_read(self, reader: asyncio.StreamReader) -> None:
        """Read lines from the gateway until the connection drops."""
        while True:
            line = await reader.readline()
            if not line:
                return
            decoded = line.decode("utf-8", errors="ignore").strip()
            if decoded:
                _LOGGER.debug("Received RFLink data: %s", decoded)
                self.async_handle_line(decoded)

    async def _async_keepalive(self) -> None:
        """Ping the gateway so a dead link is detected."""
        while True:
            await asyncio.sleep(self.keepalive_interval)
            try:
                await self.async_send_raw("10;PING;", repetitions=1)
            except OSError as err:
                _LOGGER.debug("Keep-alive ping failed: %s", err)
                return

    @callback
    def _set_connected(self, connected: bool) -> None:
        self.is_connected = connected
        async_dispatcher_send(
            self.hass, SIGNAL_CONNECTION.format(self.entry.entry_id), connected
        )

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    async def async_send_raw(
        self, packet: str, *, repetitions: int | None = None
    ) -> None:
        """Write a raw packet to the gateway."""
        if not self._writer or not self.is_connected:
            raise ConnectionError(f"RFLink gateway on {self.port} is disconnected")

        payload = packet if packet.endswith("\n") else f"{packet}\n"
        count = self.signal_repetitions if repetitions is None else repetitions
        async with self._send_lock:
            for _ in range(max(1, count)):
                _LOGGER.debug("Sending RFLink packet: %s", payload.strip())
                self._writer.write(payload.encode("utf-8"))
                await self._writer.drain()

    async def async_send_command(
        self, protocol: str, device_id: str, switch: str, command: str
    ) -> None:
        """Send a switch style command."""
        await self.async_send_raw(f"10;{protocol};{device_id};{switch};{command};")

    # ------------------------------------------------------------------
    # Receiving
    # ------------------------------------------------------------------

    @callback
    def async_handle_line(self, line: str) -> None:
        """Handle a single raw line coming from the gateway."""
        self.packets_received += 1
        if (packet := parse_packet(line)) is None:
            return

        entry_id = self.entry.entry_id
        now = dt_util.utcnow()
        self.last_seen[packet.device_id] = now
        self.last_packet[packet.device_id] = packet
        if packet.legacy_device_id:
            self.last_packet[packet.legacy_device_id] = packet

        async_dispatcher_send(
            self.hass, SIGNAL_DEVICE_UPDATE.format(entry_id, packet.device_id), packet
        )
        if packet.legacy_device_id:
            async_dispatcher_send(
                self.hass,
                SIGNAL_DEVICE_UPDATE.format(entry_id, packet.legacy_device_id),
                packet,
            )
        if packet.group_id and packet.command in COMMANDS_GROUP:
            async_dispatcher_send(
                self.hass, SIGNAL_GROUP_UPDATE.format(entry_id, packet.group_id), packet
            )

        self._async_track_discovery(packet, now)

    @callback
    def _async_track_discovery(self, packet: RFLinkPacket, now: datetime) -> None:
        """Remember every device seen, and add unknown ones when asked to."""
        self.seen[packet.device_id] = DiscoveredDevice(
            device_id=packet.device_id,
            device_type=packet.device_type,
            protocol=packet.protocol,
            fields=dict(packet.fields),
            last_seen=now,
        )
        while len(self.seen) > DISCOVERY_BUFFER_SIZE:
            self.seen.pop(next(iter(self.seen)))

        if not self.automatic_add:
            return

        configured = self.async_configured_device_ids()
        if packet.device_id in configured:
            return
        if packet.legacy_device_id and packet.legacy_device_id in configured:
            return
        self._async_create_subentry(packet)

    @callback
    def _async_create_subentry(self, packet: RFLinkPacket) -> None:
        """Automatically add a newly seen device as a subentry."""
        subentry_type = (
            SUBENTRY_TYPE_SENSOR
            if packet.device_type == "sensor"
            else SUBENTRY_TYPE_SWITCH
        )
        subentry = ConfigSubentry(
            data={CONF_DEVICE_ID: packet.device_id, CONF_ALIASES: []},
            subentry_id=ulid_util.ulid_now(),
            subentry_type=subentry_type,
            title=packet.device_id,
            unique_id=packet.device_id,
        )
        _LOGGER.info(
            "Automatically adding discovered RFLink device %s as %s",
            packet.device_id,
            subentry_type,
        )
        self.hass.config_entries.async_add_subentry(self.entry, subentry)

    @callback
    def async_clear_discovered(self) -> None:
        """Forget every buffered discovery."""
        self.seen.clear()


@callback
def async_subentry_device_ids(subentry: ConfigSubentry) -> list[str]:
    """Return the device id and all aliases of a subentry."""
    device_ids = [subentry.data[CONF_DEVICE_ID]]
    device_ids.extend(subentry.data.get(CONF_ALIASES, []))
    return device_ids
