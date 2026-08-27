<img src="custom_components/rflink_ui/brand/logo.png" alt="RFLink UI" width="360">

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![Quality scale](https://img.shields.io/badge/quality%20scale-silver-c0c0c0.svg)](https://developers.home-assistant.io/docs/core/integration-quality-scale/)

**RFLink UI** is a fully UI driven [Home Assistant](https://www.home-assistant.io)
integration for Arduino RFLink gateways. Unlike the legacy YAML based `rflink`
integration, every device is added, renamed, reconfigured and removed straight
from the Home Assistant interface.

> Based on [guanaco0403/Home-Assistant-Rflink-UI](https://github.com/guanaco0403/Home-Assistant-Rflink-UI),
> rebuilt for current Home Assistant standards. See [CHANGELOG.md](CHANGELOG.md).

---

## Highlights

- **Zero YAML.** The gateway is added through a config flow, devices are added as
  config subentries with their own *Add device* button on the integration card.
- **Automatic discovery.** The gateway is discovered over USB, and with
  *Automatically add new devices* enabled every 433 MHz signal that is picked up
  becomes a device without a restart or a reload.
- **A sensor is a sensor.** Every measurement in a packet becomes its own entity
  with the right device class, unit and state class. Temperature, humidity,
  pressure, wind speed, wind direction, gusts, rain, rain rate, UV, lux, CO2,
  noise, power, current, voltage, distance and more.
- **Aliases.** RFLink sometimes decodes the same physical sensor as a different
  brand. Map several IDs onto one device instead of ending up with duplicates.
- **Group commands.** `ALLON` and `ALLOFF` from a remote reach every button of
  that address.
- **Stable F007_TH identities.** Ambient Weather / Froggit sensors are addressed
  by their channel, so a battery change no longer creates a new device.

---

## Supported entities

| Platform | What you get |
| --- | --- |
| `sensor` | One entity per measurement, plus a diagnostic **Last seen** timestamp and battery status. |
| `binary_sensor` | Motion detectors, door and window contacts, smoke alarms, doorbells and leak sensors, with an optional off delay. Also a connectivity sensor for the gateway itself. |
| `switch` | RF outlets, relays and wall switches. Repeated remote presses always fire a state change, so scene remotes work. |
| `light` | Dimmers and light switches with four command styles (see below). |
| `cover` | Roller shutters and blinds with open, close and stop, and an option for protocols where up and down are reversed. |
| `radio_frequency` | The gateway transmitter, used as the target of the `send_command` and `send_raw` actions. |

### Light command styles

| Style | Behaviour |
| --- | --- |
| `dimmable` | Sends a numeric level `0-15`. |
| `hybrid` | Sends the level, then `ON`. Needed by devices such as the Telldus/Nexa MYCR-250. |
| `switchable` | Only sends `ON` and `OFF`. |
| `toggle` | Sends `ON` to flip the state. |

---

## Requirements

- Home Assistant **2026.5.4** or newer
- Python 3.14 or newer
- An Arduino based RFLink gateway on USB, or reachable over `ser2net`

`pyserial-asyncio-fast` and `pyserial` are installed automatically.

---

## Installation

### HACS (recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?repository=RFLinkUI&owner=DSorlov&category=integration)

1. **HACS → Integrations → ⋮ → Custom repositories**
2. Add `https://github.com/DSorlov/RFLinkUI` as an **Integration**
3. Install **RFLink UI** and restart Home Assistant

### Manual

1. Download the latest release
2. Copy the `rflink_ui` folder into `/config/custom_components/`
3. Restart Home Assistant

---

## Setting up the gateway

If the gateway is plugged into USB, Home Assistant discovers it and offers it
under **Settings → Devices & services**. Otherwise:

1. **Settings → Devices & services → Add integration → RFLink UI**
2. Pick your serial port. Prefer a `/dev/serial/by-id/…` path, it survives a
   reboot even when the device number changes.
3. For a network gateway choose **Enter manually** and use a URL:
   - ser2net / plain TCP: `socket://192.168.1.50:2001`
   - RFC 2217: `rfc2217://192.168.1.50:2001`

The port can be changed later with **⋮ → Reconfigure**.

### Gateway options

**⋮ → Configure** on the integration card:

| Option | Default | What it does |
| --- | --- | --- |
| Automatically add new devices | Off | Creates a device as soon as an unknown signal is received. Turn it on while pairing, then off again. |
| Command repetitions | 1 | How many times each outgoing command is sent. Raise it for devices that miss commands. |
| Keep-alive interval | 60 s | How often a `PING` is sent to detect a dead link. |

---

## Adding devices

Press **Add device** on the integration card and pick the type. The **RFLink ID**
field is a combo box: recently received signals are listed with the fields they
carry, and you can type an ID by hand such as `NewKaku_008cbc9b_1`.

Every device also accepts **Additional IDs**. Use them when RFLink decodes the
same hardware under more than one protocol, for example a sensor that is
sometimes reported as `Xiron_4b02` and sometimes as `Tunex_4b02`.

Devices are reconfigured and deleted from the same card, and renaming a device
in Home Assistant no longer touches its RFLink ID.

### Automatic discovery

With **Automatically add new devices** enabled, any packet from an unknown
device creates a device immediately: sensor packets become a sensor device,
command packets become a switch. Change the type afterwards by deleting the
device and adding it as a light, cover or binary sensor instead.

---

## Actions

### `rflink_ui.send_command`

Sends a protocol command through the gateway.

```yaml
action: rflink_ui.send_command
target:
  entity_id: radio_frequency.rflink_dev_ttyusb0_transmitter
data:
  protocol: Unitec
  command: "1a4a;4;ON"
```

### `rflink_ui.send_raw`

Sends a complete packet without any processing. This is how you drive the
gateway's own GPIO pins.

```yaml
action: rflink_ui.send_raw
target:
  entity_id: radio_frequency.rflink_dev_ttyusb0_transmitter
data:
  packet: "10;GPIOset;32;0;ON;"
```

### `rflink_ui.simulate_packet`

Feeds a packet into the integration as if it had been received. Useful for
testing automations, and for adding devices you do not have at hand.

```yaml
action: rflink_ui.simulate_packet
data:
  packet: "20;01;Kaku;ID=1234abcd;SWITCH=1;CMD=ON;"
```

---

## Troubleshooting

**"Could not open that port"**
Another integration or the legacy `rflink` integration is holding the port. Do
not run both on the same gateway.

**No devices show up in the picker**
Press a button on the remote, then reopen the *Add device* dialog. Enable debug
logging to confirm packets are arriving at all:

```yaml
logger:
  logs:
    custom_components.rflink_ui: debug
```

**A sensor's "last updated" never changes**
Home Assistant only records a change when the value changes. Turn on **Update on
every reading** for that device, or use its **Last seen** sensor, which always
reflects the most recent packet.

**A sensor gets a new device after a battery change**
For F007_TH this is handled automatically through the channel. For other
protocols, reconfigure the device and put the new ID in **Additional IDs**.

**Sending a command does nothing**
Increase **Command repetitions**. Cheap receivers often need the command two or
three times.

### Known limitations

- Outgoing commands are fire and forget. RFLink does not report whether a device
  actually reacted, so switches, lights and covers use assumed state.
- The transmitter entity cannot send raw timing sequences; RFLink only speaks its
  own protocol names. Use `send_command` or `send_raw`.
- Sub-devices are identified by their RFLink ID. If a protocol changes the ID of
  a device, add the new ID as an alias.

---

## Upgrading from 1.x

The first start after the update migrates automatically:

- Devices stored in the old options dictionaries become config subentries.
- Existing entity IDs, names and history are preserved.
- Extra measurements that used to be attributes on the temperature entity
  (wind, pressure, rain rate and so on) become entities of their own. Update
  templates and automations that read those attributes.
- The config entry gains a unique ID so the same gateway cannot be added twice.

---

## Development

```bash
pip install -r requirements_test.txt

pytest                                   # run the test suite
ruff check custom_components tests       # lint
ruff format custom_components tests      # format
python scripts/generate_brand.py         # regenerate the brand images
```

`scripts/test_runner.py` does the same thing in a throwaway virtualenv if you
prefer not to install the dependencies globally.

---

## Contributing

Pull requests are welcome. Adding a new measurement usually means one entry in
`SENSOR_TYPES` in `custom_components/rflink_ui/sensor.py` plus a name in
`strings.json`; please include the raw packet from your device in the PR.
## Credits

This project started from
[guanaco0403/Home-Assistant-Rflink-UI](https://github.com/guanaco0403/Home-Assistant-Rflink-UI)
and keeps its full history. All credit for the original integration goes there.

- [@guanaco0403](https://github.com/guanaco0403) — original author
- [@bazeman101](https://github.com/bazeman101) — cover platform
- Value decoding follows the [python-rflink](https://github.com/aequitas/python-rflink) reference implementation

## License

MIT — see [LICENSE](LICENSE).
