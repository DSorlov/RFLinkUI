"""The RFLink UI integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.const import CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import ulid as ulid_util

from .const import (
    CONF_ALIASES,
    CONF_DEVICE_ID,
    CONF_LIGHT_TYPE,
    CONF_OFF_DELAY,
    CONFIG_ENTRY_VERSION,
    DOMAIN,
    LIGHT_TYPE_DIMMABLE,
    PLATFORMS,
    RADIO_FREQUENCY_PLATFORM,
    SUBENTRY_TYPE_BINARY_SENSOR,
    SUBENTRY_TYPE_LIGHT,
    SUBENTRY_TYPE_SENSOR,
    SUBENTRY_TYPE_SWITCH,
)
from .gateway import RFLinkConfigEntry, RFLinkGateway
from .services import async_setup_services

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)

_ALL_PLATFORMS: list[Platform | str] = [*PLATFORMS, RADIO_FREQUENCY_PLATFORM]

#: Legacy option key -> subentry type
_LEGACY_OPTION_KEYS = {
    "switches": SUBENTRY_TYPE_SWITCH,
    "sensors": SUBENTRY_TYPE_SENSOR,
    "binary_sensors": SUBENTRY_TYPE_BINARY_SENSOR,
    "lights": SUBENTRY_TYPE_LIGHT,
}


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the RFLink UI integration."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: RFLinkConfigEntry) -> bool:
    """Set up RFLink UI from a config entry."""
    gateway = RFLinkGateway(hass, entry)
    entry.runtime_data = gateway

    await hass.config_entries.async_forward_entry_setups(entry, _ALL_PLATFORMS)

    for subentry in entry.subentries.values():
        gateway.async_add_subentry_entities(subentry)

    gateway.async_start()
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: RFLinkConfigEntry) -> bool:
    """Unload a config entry."""
    await entry.runtime_data.async_stop()
    return await hass.config_entries.async_unload_platforms(entry, _ALL_PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: RFLinkConfigEntry) -> None:
    """Add entities for new subentries, reload for anything else."""
    gateway = entry.runtime_data
    known = gateway.known_subentries
    current = {
        subentry_id: dict(subentry.data)
        for subentry_id, subentry in entry.subentries.items()
    }

    if set(known) - set(current) or any(
        known[subentry_id] != current[subentry_id]
        for subentry_id in set(known) & set(current)
    ):
        await hass.config_entries.async_reload(entry.entry_id)
        return

    added = set(current) - set(known)
    gateway.known_subentries = current
    for subentry_id in added:
        gateway.async_add_subentry_entities(entry.subentries[subentry_id])


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: RFLinkConfigEntry, device_entry: dr.DeviceEntry
) -> bool:
    """Allow deleting devices that no longer have a subentry."""
    configured = {
        subentry.data.get(CONF_DEVICE_ID) for subentry in entry.subentries.values()
    }
    configured.add(entry.entry_id)
    return not any(
        identifier[0] == DOMAIN and identifier[1] in configured
        for identifier in device_entry.identifiers
    )


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old config entries to the subentry based layout."""
    if entry.version > CONFIG_ENTRY_VERSION:
        # Downgrading from a future version is not supported.
        return False

    if entry.version == 1:
        _LOGGER.debug("Migrating RFLink UI entry %s to version 2", entry.title)
        _migrate_options_to_subentries(hass, entry)
        hass.config_entries.async_update_entry(
            entry,
            options={
                key: value
                for key, value in entry.options.items()
                if key not in _LEGACY_OPTION_KEYS
            },
            unique_id=entry.data[CONF_PORT],
            version=2,
        )

    return True


def _migrate_options_to_subentries(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Turn the legacy options dictionaries into config subentries."""
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)

    for option_key, subentry_type in _LEGACY_OPTION_KEYS.items():
        for device_id, config in entry.options.get(option_key, {}).items():
            data: dict = {CONF_DEVICE_ID: device_id, CONF_ALIASES: []}
            if isinstance(config, dict):
                name = config.get("name") or device_id
                if subentry_type == SUBENTRY_TYPE_BINARY_SENSOR:
                    data["device_class"] = config.get("device_class")
                    data[CONF_OFF_DELAY] = config.get(CONF_OFF_DELAY)
                elif subentry_type == SUBENTRY_TYPE_LIGHT:
                    data[CONF_LIGHT_TYPE] = config.get("type", LIGHT_TYPE_DIMMABLE)
            else:
                name = config or device_id
                if subentry_type == SUBENTRY_TYPE_LIGHT:
                    data[CONF_LIGHT_TYPE] = LIGHT_TYPE_DIMMABLE

            subentry = ConfigSubentry(
                data=data,
                subentry_id=ulid_util.ulid_now(),
                subentry_type=subentry_type,
                title=name,
                unique_id=device_id,
            )
            hass.config_entries.async_add_subentry(entry, subentry)
            _reassign_registry_entries(ent_reg, dev_reg, entry, subentry, device_id)


def _reassign_registry_entries(
    ent_reg: er.EntityRegistry,
    dev_reg: dr.DeviceRegistry,
    entry: ConfigEntry,
    subentry: ConfigSubentry,
    device_id: str,
) -> None:
    """Move existing devices and entities into their new subentry."""
    device = dev_reg.async_get_device(identifiers={(DOMAIN, device_id)})
    if device is None:
        return

    dev_reg.async_update_device(
        device.id,
        add_config_entry_id=entry.entry_id,
        add_config_subentry_id=subentry.subentry_id,
        remove_config_entry_id=entry.entry_id,
        remove_config_subentry_id=None,
    )
    for registry_entry in er.async_entries_for_device(
        ent_reg, device.id, include_disabled_entities=True
    ):
        ent_reg.async_update_entity(
            registry_entry.entity_id, config_subentry_id=subentry.subentry_id
        )
