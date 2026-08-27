# Changelog

## 2.0.0

A large modernisation release. Existing configurations migrate automatically on
the first start; entity IDs and history are preserved.

### Breaking changes

- Devices moved from the options flow to **config subentries**. They now have
  their own *Add device* button on the integration card, and each device can be
  reconfigured and deleted individually.
- Extra measurements are no longer attributes. Fields such as wind speed,
  pressure and rain rate that used to live on the temperature entity are now
  entities of their own. Templates and automations that read those attributes
  need to be updated.
- The config entry now has a unique ID (the serial port), so the same gateway
  cannot be added twice.
- `pyserial-asyncio-fast` is used directly; the `serial_asyncio` shim is gone.

### Added

- USB discovery: Arduino based gateways are offered automatically
  (Settings → Devices & services).
- *Automatically add new devices*: any unknown 433 MHz signal creates a device
  immediately, without a restart or reload.
- Full RFLink field coverage as dedicated entities with the correct device
  class, unit and state class: `BARO`, `HSTATUS`, `BFORECAST`, `UV`, `LUX`,
  `RAINRATE`, `WINSP`, `AWINSP`, `WINGS`, `WINDIR`, `WINCHL`, `WINTMP`, `CO2`,
  `SOUND`, `WATT`, `KWATT`, `CURRENT`, `CURRENT2`, `CURRENT3`, `VOLT`, `DIST`,
  `METER` and `CHIME`, next to the existing temperature, humidity, battery and
  rain entities.
- `PIR` and `SMOKEALERT` fields become binary sensors (#19 related hardware).
- **Cover** platform for roller shutters and blinds, including an *inverted*
  option for protocols where up and down are swapped. Based on the work of
  @bazeman101 (#13, #14).
- **Aliases**: several RFLink IDs can map onto one device, for protocols that
  are sometimes decoded under a different brand (#21).
- **Last seen** diagnostic timestamp per device, plus a per device *Update on
  every reading* option, for reacting to unchanged readings (#20).
- `ALLON` / `ALLOFF` group commands now reach every button of an address (#19).
- `rflink_ui.send_raw` action for gateway commands such as `10;GPIOset;32;0;ON;`
  (#10).
- Reconfigure flow for changing the serial port.
- Gateway options for command repetitions and keep-alive interval.
- Diagnostics download, entity and exception translations, icon translations,
  Swedish translation, and a `quality_scale.yaml`.
- Local brand images in `custom_components/rflink_ui/brand/`, supported by Home
  Assistant 2026.3 and newer.

### Changed

- Runtime state moved from `hass.data` to `entry.runtime_data` with a typed
  config entry.
- The serial connection was extracted into a `RFLinkGateway` class with
  exponential reconnect backoff that no longer floods the log.
- Entities become unavailable while the gateway is disconnected.
- Device IDs are split from the right, so protocol names containing an
  underscore such as `F007_TH` are handled correctly.
- Value decoding follows the `python-rflink` reference implementation.
- Adding a device no longer reloads the whole integration.
- Brightness mapping between Home Assistant (0-255) and RFLink (0-15) is now
  symmetric, so a dimmer set to 100% reports 100%.
- CI runs ruff, codespell, hassfest, HACS validation and the test suite on
  Python 3.13 and 3.14.

### Fixed

- Switch, light and cover commands raise a proper, translated error instead of
  silently doing nothing when the gateway is disconnected.
- The off delay listener is cancelled when a binary sensor is removed.
