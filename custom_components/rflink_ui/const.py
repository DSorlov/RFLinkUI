"""Constants for the RFLink UI integration."""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "rflink_ui"

CONFIG_ENTRY_VERSION: Final = 2

DEFAULT_BAUDRATE: Final = 57600
DEFAULT_RECONNECT_INTERVAL: Final = 5
MAX_RECONNECT_INTERVAL: Final = 300
KEEPALIVE_INTERVAL: Final = 60
DISCOVERY_BUFFER_SIZE: Final = 100

MANUAL_PORT: Final = "manual"

PLATFORMS: Final[list[Platform]] = [
    Platform.BINARY_SENSOR,
    Platform.COVER,
    Platform.LIGHT,
    Platform.SENSOR,
    Platform.SWITCH,
]
RADIO_FREQUENCY_PLATFORM: Final = "radio_frequency"

# Config entry / subentry keys
CONF_AUTOMATIC_ADD: Final = "automatic_add"
CONF_ALIASES: Final = "aliases"
CONF_DEVICE_ID: Final = "device_id"
CONF_FORCE_UPDATE: Final = "force_update"
CONF_INVERTED: Final = "inverted"
CONF_LIGHT_TYPE: Final = "light_type"
CONF_OFF_DELAY: Final = "off_delay"
CONF_SIGNAL_REPETITIONS: Final = "signal_repetitions"
CONF_KEEPALIVE: Final = "keepalive"

DEFAULT_AUTOMATIC_ADD: Final = False
DEFAULT_SIGNAL_REPETITIONS: Final = 1

# Subentry types, these double as the platform each subentry belongs to
SUBENTRY_TYPE_BINARY_SENSOR: Final = "binary_sensor"
SUBENTRY_TYPE_COVER: Final = "cover"
SUBENTRY_TYPE_LIGHT: Final = "light"
SUBENTRY_TYPE_SENSOR: Final = "sensor"
SUBENTRY_TYPE_SWITCH: Final = "switch"

SUBENTRY_TYPES: Final = (
    SUBENTRY_TYPE_SWITCH,
    SUBENTRY_TYPE_LIGHT,
    SUBENTRY_TYPE_COVER,
    SUBENTRY_TYPE_BINARY_SENSOR,
    SUBENTRY_TYPE_SENSOR,
)

# Light command styles
LIGHT_TYPE_DIMMABLE: Final = "dimmable"
LIGHT_TYPE_HYBRID: Final = "hybrid"
LIGHT_TYPE_SWITCHABLE: Final = "switchable"
LIGHT_TYPE_TOGGLE: Final = "toggle"
LIGHT_TYPES: Final = (
    LIGHT_TYPE_DIMMABLE,
    LIGHT_TYPE_HYBRID,
    LIGHT_TYPE_SWITCHABLE,
    LIGHT_TYPE_TOGGLE,
)

# Services
SERVICE_SEND_COMMAND: Final = "send_command"
SERVICE_SEND_RAW: Final = "send_raw"
SERVICE_SIMULATE_PACKET: Final = "simulate_packet"

ATTR_COMMAND: Final = "command"
ATTR_PACKET: Final = "packet"
ATTR_PROTOCOL: Final = "protocol"

# Dispatcher signals
SIGNAL_CONNECTION: Final = f"{DOMAIN}_connection_{{}}"
SIGNAL_DEVICE_UPDATE: Final = f"{DOMAIN}_update_{{}}_{{}}"
SIGNAL_GROUP_UPDATE: Final = f"{DOMAIN}_group_{{}}_{{}}"
SIGNAL_NEW_SENSOR_FIELD: Final = f"{DOMAIN}_new_field_{{}}_{{}}"

# Commands understood as "on" / "off" across platforms
COMMANDS_ON: Final = frozenset({"ON", "ALLON", "OPEN", "UP", "MOTION"})
COMMANDS_OFF: Final = frozenset({"OFF", "ALLOFF", "CLOSE", "DOWN"})
COMMANDS_GROUP: Final = frozenset({"ALLON", "ALLOFF"})

# RFLink payload keys that never represent a measurement
NON_SENSOR_KEYS: Final = frozenset(
    {
        "ID",
        "SWITCH",
        "CMD",
        "SET_LEVEL",
        "RGBW",
        "VER",
        "REV",
        "BUILD",
    }
)
