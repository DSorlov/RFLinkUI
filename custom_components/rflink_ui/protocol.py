"""Parsing helpers for the RFLink serial protocol.

Value conversions follow the reference implementation in the ``rflink``
Python package so that data matches the legacy ``rflink`` integration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging

_LOGGER = logging.getLogger(__name__)

GATEWAY_NODE = "20"

#: ``20;<seq>;<protocol>;<key=value>;`` is the shortest usable device packet.
MIN_PACKET_PARTS = 4

HSTATUS_LOOKUP = {
    "0": "normal",
    "1": "comfortable",
    "2": "dry",
    "3": "wet",
}

BFORECAST_LOOKUP = {
    "0": "no_info",
    "1": "sunny",
    "2": "partly_cloudy",
    "3": "cloudy",
    "4": "rain",
}


def _signed_hex_to_float(value: str) -> float:
    """Convert an RFLink signed hexadecimal temperature to a float."""
    raw = int(value, 16)
    if raw & 0x8000:
        return -(raw & 0x7FFF) / 10
    return raw / 10


def _hex_to_int(value: str) -> int:
    return int(value, 16)


def _hex_to_tenths(value: str) -> float:
    return int(value, 16) / 10


#: Converters keyed by the uppercase RFLink payload key.
VALUE_CONVERTERS = {
    "AWINSP": _hex_to_tenths,
    "BARO": _hex_to_int,
    "BFORECAST": lambda value: BFORECAST_LOOKUP.get(value, "unknown"),
    "CHIME": int,
    "CO2": int,
    "CURRENT": int,
    "CURRENT2": int,
    "CURRENT3": int,
    "DIST": int,
    "HSTATUS": lambda value: HSTATUS_LOOKUP.get(value, "unknown"),
    "HUM": int,
    "KWATT": _hex_to_int,
    "LUX": _hex_to_int,
    "METER": int,
    "RAIN": _hex_to_tenths,
    "RAINRATE": _hex_to_tenths,
    "RAINTOT": _hex_to_tenths,
    "SOUND": int,
    "TEMP": _signed_hex_to_float,
    "UV": _hex_to_int,
    "VOLT": int,
    "WATT": _hex_to_int,
    "WINCHL": _signed_hex_to_float,
    "WINDIR": lambda value: int(value) * 22.5,
    "WINGS": _hex_to_tenths,
    "WINSP": _hex_to_tenths,
    "WINTMP": _signed_hex_to_float,
}


def convert_value(key: str, raw: str) -> float | int | str:
    """Convert a raw RFLink payload value to its native representation."""
    if converter := VALUE_CONVERTERS.get(key):
        try:
            return converter(raw)
        except (ValueError, TypeError):
            _LOGGER.debug("Could not convert %s value %r", key, raw)
    return raw


@dataclass(slots=True)
class RFLinkPacket:
    """A decoded RFLink gateway packet."""

    protocol: str
    node_id: str
    fields: dict[str, str]
    device_id: str
    device_type: str
    group_id: str | None = None
    legacy_device_id: str | None = None
    aliases: list[str] = field(default_factory=list)

    @property
    def command(self) -> str | None:
        """Return the uppercased command, if this is a command packet."""
        if (cmd := self.fields.get("CMD")) is None:
            return None
        return cmd.upper()

    @property
    def sensor_keys(self) -> list[str]:
        """Return the payload keys that carry measurements."""
        from .const import NON_SENSOR_KEYS  # noqa: PLC0415  (avoid import cycle)

        return [key for key in self.fields if key not in NON_SENSOR_KEYS]


def normalize_device_id(protocol: str, device_id: str) -> tuple[str, str | None]:
    """Return a stable device id, plus the raw id when normalization applied.

    F007_TH sensors change their RFLink id on every battery replacement, but
    the lowest nibble always encodes the configured channel. Using the channel
    keeps the device identity stable across battery changes (issue #11).
    """
    if protocol == "F007_TH" and device_id:
        try:
            channel = (int(device_id[-1], 16) & 0x07) + 1
        except (ValueError, IndexError):
            return f"{protocol}_{device_id}", None
        return f"{protocol}_CH{channel}", f"{protocol}_{device_id}"
    return f"{protocol}_{device_id}", None


def split_device_id(device_id: str, *, with_switch: bool) -> tuple[str, str, str]:
    """Split a device id into protocol, id and switch.

    Splitting happens from the right so protocol names that contain an
    underscore (for example ``F007_TH``) are handled correctly.
    """
    wanted = 3 if with_switch else 2
    parts = device_id.rsplit("_", wanted - 1)
    if len(parts) != wanted:
        return device_id, "0", "0"
    if with_switch:
        return parts[0], parts[1], parts[2]
    return parts[0], parts[1], "0"


def parse_packet(line: str) -> RFLinkPacket | None:
    """Parse a raw RFLink line into a packet, or return None if unusable."""
    parts = line.split(";")
    if len(parts) < MIN_PACKET_PARTS or parts[0] != GATEWAY_NODE:
        return None

    protocol = parts[2]
    fields: dict[str, str] = {}
    for part in parts[3:]:
        if "=" in part:
            key, value = part.split("=", 1)
            fields[key.upper()] = value

    device_id = fields.get("ID")
    if not protocol or not device_id:
        return None

    if "CMD" in fields:
        switch = fields.get("SWITCH", "0")
        return RFLinkPacket(
            protocol=protocol,
            node_id=parts[1],
            fields=fields,
            device_id=f"{protocol}_{device_id}_{switch}",
            device_type="switch",
            group_id=f"{protocol}_{device_id}",
        )

    normalized, legacy = normalize_device_id(protocol, device_id)
    return RFLinkPacket(
        protocol=protocol,
        node_id=parts[1],
        fields=fields,
        device_id=normalized,
        device_type="sensor",
        legacy_device_id=legacy,
    )
