"""Config flow for the RFLink UI integration."""

from __future__ import annotations

import glob
from pathlib import Path
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.const import CONF_DEVICE_CLASS, CONF_NAME, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)
from homeassistant.helpers.service_info.usb import UsbServiceInfo
import serial
import serial.tools.list_ports
import voluptuous as vol

from .const import (
    CONF_ALIASES,
    CONF_AUTOMATIC_ADD,
    CONF_DEVICE_ID,
    CONF_FORCE_UPDATE,
    CONF_INVERTED,
    CONF_KEEPALIVE,
    CONF_LIGHT_TYPE,
    CONF_OFF_DELAY,
    CONF_SIGNAL_REPETITIONS,
    CONFIG_ENTRY_VERSION,
    DEFAULT_AUTOMATIC_ADD,
    DEFAULT_BAUDRATE,
    DEFAULT_SIGNAL_REPETITIONS,
    DOMAIN,
    KEEPALIVE_INTERVAL,
    LIGHT_TYPE_DIMMABLE,
    LIGHT_TYPES,
    MANUAL_PORT,
    SUBENTRY_TYPE_BINARY_SENSOR,
    SUBENTRY_TYPE_COVER,
    SUBENTRY_TYPE_LIGHT,
    SUBENTRY_TYPE_SENSOR,
    SUBENTRY_TYPE_SWITCH,
)


def _test_serial_port(port: str) -> None:
    """Open the port to verify it is reachable."""
    with serial.serial_for_url(port, DEFAULT_BAUDRATE, timeout=1):
        pass


class RFLinkConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for RFLink UI."""

    VERSION = CONFIG_ENTRY_VERSION

    def __init__(self) -> None:
        """Initialize the flow."""
        self._discovered_port: str | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return RFLinkOptionsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return the device types that can be added to a gateway."""
        return {
            SUBENTRY_TYPE_SWITCH: SwitchSubentryFlow,
            SUBENTRY_TYPE_LIGHT: LightSubentryFlow,
            SUBENTRY_TYPE_COVER: CoverSubentryFlow,
            SUBENTRY_TYPE_BINARY_SENSOR: BinarySensorSubentryFlow,
            SUBENTRY_TYPE_SENSOR: SensorSubentryFlow,
        }

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            port = user_input[CONF_PORT]
            if port == MANUAL_PORT:
                return await self.async_step_manual_port()
            if not (errors := await self._async_validate(port)):
                return await self._async_create(port)

        port_list = await self.hass.async_add_executor_job(_available_ports)
        options = [SelectOptionDict(value=port, label=port) for port in port_list]
        options.append(SelectOptionDict(value=MANUAL_PORT, label="Enter manually…"))

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PORT): SelectSelector(
                        SelectSelectorConfig(
                            options=options, mode=SelectSelectorMode.DROPDOWN
                        )
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_manual_port(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle manual port or network URL entry."""
        errors: dict[str, str] = {}

        if user_input is not None:
            port = user_input[CONF_PORT]
            if not (errors := await self._async_validate(port)):
                return await self._async_create(port)

        return self.async_show_form(
            step_id="manual_port",
            data_schema=vol.Schema({vol.Required(CONF_PORT): TextSelector()}),
            errors=errors,
        )

    async def async_step_usb(self, discovery_info: UsbServiceInfo) -> ConfigFlowResult:
        """Handle a gateway discovered on the USB bus."""
        device = await self.hass.async_add_executor_job(
            _serial_by_id, discovery_info.device
        )
        await self.async_set_unique_id(device)
        self._abort_if_unique_id_configured(updates={CONF_PORT: device})
        self._discovered_port = device
        self.context["title_placeholders"] = {"name": device}
        return await self.async_step_usb_confirm()

    async def async_step_usb_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm setup of a discovered gateway."""
        assert self._discovered_port is not None
        errors: dict[str, str] = {}

        if user_input is not None and not (
            errors := await self._async_validate(self._discovered_port)
        ):
            return await self._async_create(self._discovered_port)

        return self.async_show_form(
            step_id="usb_confirm",
            description_placeholders={"port": self._discovered_port},
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the serial port of an existing gateway."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            port = user_input[CONF_PORT]
            if not (errors := await self._async_validate(port)):
                await self.async_set_unique_id(port)
                self._abort_if_unique_id_mismatch(reason="wrong_port")
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PORT: port}
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {vol.Required(CONF_PORT, default=entry.data[CONF_PORT]): TextSelector()}
            ),
            errors=errors,
        )

    async def _async_validate(self, port: str) -> dict[str, str]:
        """Return form errors for a port that cannot be opened."""
        try:
            await self.hass.async_add_executor_job(_test_serial_port, port)
        except (OSError, serial.SerialException, ValueError):
            return {"base": "cannot_connect"}
        return {}

    async def _async_create(self, port: str) -> ConfigFlowResult:
        """Create the config entry for a validated port."""
        await self.async_set_unique_id(port)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=f"RFLink ({port})", data={CONF_PORT: port})


def _serial_by_id(device: str) -> str:
    """Return the stable /dev/serial/by-id path for a device, if there is one."""
    by_id = "/dev/serial/by-id"
    if not Path(by_id).is_dir():
        return device

    resolved = Path(device).resolve()
    for candidate in sorted(Path(by_id).iterdir()):
        if candidate.resolve() == resolved:
            return str(candidate)
    return device


def _available_ports() -> list[str]:
    """Return the serial ports that look usable."""
    ports = [port.device for port in serial.tools.list_ports.comports()]
    ports.extend(sorted(glob.glob("/dev/serial/by-id/*")))
    return ports


class RFLinkOptionsFlow(OptionsFlow):
    """Handle gateway wide options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the gateway options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_AUTOMATIC_ADD,
                        default=options.get(CONF_AUTOMATIC_ADD, DEFAULT_AUTOMATIC_ADD),
                    ): BooleanSelector(),
                    vol.Required(
                        CONF_SIGNAL_REPETITIONS,
                        default=options.get(
                            CONF_SIGNAL_REPETITIONS, DEFAULT_SIGNAL_REPETITIONS
                        ),
                    ): NumberSelector(
                        NumberSelectorConfig(min=1, max=10, mode=NumberSelectorMode.BOX)
                    ),
                    vol.Required(
                        CONF_KEEPALIVE,
                        default=options.get(CONF_KEEPALIVE, KEEPALIVE_INTERVAL),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=10,
                            max=3600,
                            mode=NumberSelectorMode.BOX,
                            unit_of_measurement="s",
                        )
                    ),
                }
            ),
        )


class RFLinkSubentryFlow(ConfigSubentryFlow):
    """Shared behaviour for adding and editing RFLink devices."""

    #: Which discovery bucket to offer as suggestions.
    discovery_type = "switch"

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Add a new device."""
        if user_input is not None:
            data = self._data_from_input(user_input)
            return self.async_create_entry(
                title=user_input[CONF_NAME],
                data=data,
                unique_id=data[CONF_DEVICE_ID],
            )

        return self.async_show_form(step_id="user", data_schema=self._schema({}))

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Edit an existing device."""
        subentry = self._get_reconfigure_subentry()

        if user_input is not None:
            data = self._data_from_input(user_input)
            return self.async_update_and_abort(
                self._get_entry(),
                subentry,
                title=user_input[CONF_NAME],
                data=data,
                unique_id=data[CONF_DEVICE_ID],
            )

        defaults = {**subentry.data, CONF_NAME: subentry.title}
        return self.async_show_form(
            step_id="reconfigure", data_schema=self._schema(defaults)
        )

    @callback
    def _data_from_input(self, user_input: dict[str, Any]) -> dict[str, Any]:
        """Convert form input into subentry data."""
        data = {
            CONF_DEVICE_ID: user_input[CONF_DEVICE_ID].strip(),
            CONF_ALIASES: [alias.strip() for alias in user_input.get(CONF_ALIASES, [])],
        }
        data.update(self._extra_data(user_input))
        return data

    @callback
    def _extra_data(self, user_input: dict[str, Any]) -> dict[str, Any]:
        """Return the platform specific part of the subentry data."""
        return {}

    @callback
    def _schema(self, defaults: dict[str, Any]) -> vol.Schema:
        """Build the form schema."""
        device_options = self._device_options()
        schema: dict[Any, Any] = {
            vol.Required(
                CONF_DEVICE_ID, default=defaults.get(CONF_DEVICE_ID, vol.UNDEFINED)
            ): SelectSelector(
                SelectSelectorConfig(
                    options=device_options,
                    custom_value=True,
                    mode=SelectSelectorMode.DROPDOWN,
                    sort=True,
                )
            ),
            vol.Required(
                CONF_NAME, default=defaults.get(CONF_NAME, vol.UNDEFINED)
            ): TextSelector(),
        }
        schema.update(self._extra_schema(defaults))
        schema[vol.Optional(CONF_ALIASES, default=defaults.get(CONF_ALIASES, []))] = (
            SelectSelector(
                SelectSelectorConfig(
                    options=device_options,
                    custom_value=True,
                    multiple=True,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )
        )
        return vol.Schema(schema)

    @callback
    def _extra_schema(self, defaults: dict[str, Any]) -> dict[Any, Any]:
        """Return the platform specific part of the form schema."""
        return {}

    @callback
    def _device_options(self) -> list[SelectOptionDict]:
        """Return recently seen devices that match this platform."""
        entry = self._get_entry()
        gateway = getattr(entry, "runtime_data", None)
        if gateway is None:
            return []

        return [
            SelectOptionDict(
                value=device.device_id,
                label=f"{device.device_id} ({', '.join(sorted(device.fields))})",
            )
            for device in gateway.discovered.values()
            if device.device_type == self.discovery_type
        ]


class SwitchSubentryFlow(RFLinkSubentryFlow):
    """Add or edit a switch."""


class LightSubentryFlow(RFLinkSubentryFlow):
    """Add or edit a light."""

    @callback
    def _extra_schema(self, defaults: dict[str, Any]) -> dict[Any, Any]:
        return {
            vol.Required(
                CONF_LIGHT_TYPE,
                default=defaults.get(CONF_LIGHT_TYPE, LIGHT_TYPE_DIMMABLE),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=list(LIGHT_TYPES),
                    mode=SelectSelectorMode.DROPDOWN,
                    translation_key="light_type",
                )
            )
        }

    @callback
    def _extra_data(self, user_input: dict[str, Any]) -> dict[str, Any]:
        return {CONF_LIGHT_TYPE: user_input[CONF_LIGHT_TYPE]}


class CoverSubentryFlow(RFLinkSubentryFlow):
    """Add or edit a cover."""

    @callback
    def _extra_schema(self, defaults: dict[str, Any]) -> dict[Any, Any]:
        return {
            vol.Required(
                CONF_INVERTED, default=defaults.get(CONF_INVERTED, False)
            ): BooleanSelector()
        }

    @callback
    def _extra_data(self, user_input: dict[str, Any]) -> dict[str, Any]:
        return {CONF_INVERTED: user_input[CONF_INVERTED]}


class BinarySensorSubentryFlow(RFLinkSubentryFlow):
    """Add or edit a binary sensor."""

    @callback
    def _extra_schema(self, defaults: dict[str, Any]) -> dict[Any, Any]:
        return {
            vol.Optional(
                CONF_DEVICE_CLASS,
                description={"suggested_value": defaults.get(CONF_DEVICE_CLASS)},
            ): SelectSelector(
                SelectSelectorConfig(
                    options=sorted(
                        device_class.value for device_class in BinarySensorDeviceClass
                    ),
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_OFF_DELAY,
                description={"suggested_value": defaults.get(CONF_OFF_DELAY)},
            ): NumberSelector(
                NumberSelectorConfig(
                    min=1,
                    max=3600,
                    mode=NumberSelectorMode.BOX,
                    unit_of_measurement="s",
                )
            ),
        }

    @callback
    def _extra_data(self, user_input: dict[str, Any]) -> dict[str, Any]:
        off_delay = user_input.get(CONF_OFF_DELAY)
        return {
            CONF_DEVICE_CLASS: user_input.get(CONF_DEVICE_CLASS),
            CONF_OFF_DELAY: int(off_delay) if off_delay else None,
        }


class SensorSubentryFlow(RFLinkSubentryFlow):
    """Add or edit a sensor device."""

    discovery_type = "sensor"

    @callback
    def _extra_schema(self, defaults: dict[str, Any]) -> dict[Any, Any]:
        return {
            vol.Required(
                CONF_FORCE_UPDATE, default=defaults.get(CONF_FORCE_UPDATE, False)
            ): BooleanSelector()
        }

    @callback
    def _extra_data(self, user_input: dict[str, Any]) -> dict[str, Any]:
        return {CONF_FORCE_UPDATE: user_input[CONF_FORCE_UPDATE]}
