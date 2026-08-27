"""Tests for the RFLink packet parser."""

from __future__ import annotations

import pytest

from custom_components.rflink_ui.protocol import (
    convert_value,
    normalize_device_id,
    parse_packet,
    split_device_id,
)


def test_parse_switch_packet() -> None:
    """A command packet becomes a switch device with a group id."""
    packet = parse_packet("20;06;NewKaku;ID=008cbc9b;SWITCH=1;CMD=OFF;")

    assert packet is not None
    assert packet.protocol == "NewKaku"
    assert packet.device_id == "NewKaku_008cbc9b_1"
    assert packet.group_id == "NewKaku_008cbc9b"
    assert packet.device_type == "switch"
    assert packet.command == "OFF"


def test_parse_sensor_packet() -> None:
    """A sensor packet exposes only its measurement keys."""
    packet = parse_packet("20;3A;Oregon TempHygro;ID=0A4C;TEMP=00ba;HUM=40;BAT=OK;")

    assert packet is not None
    assert packet.device_id == "Oregon TempHygro_0A4C"
    assert packet.device_type == "sensor"
    assert packet.command is None
    assert sorted(packet.sensor_keys) == ["BAT", "HUM", "TEMP"]


@pytest.mark.parametrize(
    "line",
    [
        "20;01;OK;",
        "10;NewKaku;008cbc9b;1;ON;",
        "20;00;Nodo RadioFrequencyLink - RFLink Gateway V1.1 - R48;",
    ],
)
def test_parse_ignores_non_device_lines(line: str) -> None:
    """Lines that do not describe a device are ignored."""
    assert parse_packet(line) is None


def test_f007_th_channel_normalization() -> None:
    """F007_TH ids collapse onto their stable channel."""
    normalized, legacy = normalize_device_id("F007_TH", "45246")

    assert normalized == "F007_TH_CH7"
    assert legacy == "F007_TH_45246"


def test_split_device_id_handles_underscore_protocols() -> None:
    """Protocol names containing an underscore split correctly."""
    assert split_device_id("F007_TH_45246_1", with_switch=True) == (
        "F007_TH",
        "45246",
        "1",
    )
    assert split_device_id("F007_TH_CH7", with_switch=False) == ("F007_TH", "CH7", "0")


@pytest.mark.parametrize(
    ("key", "raw", "expected"),
    [
        ("TEMP", "00ba", 18.6),
        ("TEMP", "80ba", -18.6),
        ("HUM", "40", 40),
        ("BARO", "03e8", 1000),
        ("RAIN", "0010", 1.6),
        ("WINDIR", "4", 90.0),
        ("WINSP", "0032", 5.0),
        ("HSTATUS", "2", "dry"),
        ("BFORECAST", "4", "rain"),
        ("BAT", "OK", "OK"),
    ],
)
def test_convert_value(key: str, raw: str, expected) -> None:
    """Raw payload values decode to their native representation."""
    assert convert_value(key, raw) == expected


def test_convert_value_survives_garbage() -> None:
    """A value that cannot be converted is passed through untouched."""
    assert convert_value("TEMP", "zzzz") == "zzzz"
