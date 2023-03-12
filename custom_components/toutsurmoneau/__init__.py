import logging

from homeassistant import config_entries, core

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def options_update_listener(
    hass: core.HomeAssistant, config_entry: config_entries.ConfigEntry
):
    """
    Handle options update -- just reload all the entries
    """
    _LOGGER.debug(f"options_update_listener {config_entry=}")
    await hass.config_entries.async_reload(config_entry.entry_id)

async def async_setup_entry(
    hass: core.HomeAssistant, entry: config_entries.ConfigEntry
) -> bool:
    """
    Set up platform from a ConfigEntry
    """
    hass.data.setdefault(DOMAIN, {})
    hass_data = {
        **entry.data,
        **entry.options,
        "unsubscribe": entry.add_update_listener(options_update_listener)
    }
    _LOGGER.debug(f"setup entry: {entry.data=}, {entry.options=}")
    hass.data[DOMAIN][entry.entry_id] = hass_data
    _LOGGER.info(f"setup entry: setting up suez sensors")
    _LOGGER.debug(f"setup entry: with {entry.entry_id=}, {hass_data}")
    await hass.config_entries.async_forward_entry_setup(entry, "sensor")
    return True

async def async_unload_entry(
    hass: core.HomeAssistant, entry: config_entries.ConfigEntry
) -> bool:
    """
    Unload a config entry
    """
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    if unload_ok:
        _LOGGER.info(f"unload entry: removing at {entry.entry_id=}")
        hass_data = hass.data[DOMAIN][entry.entry_id]
        _LOGGER.debug(f"unload entry: {hass_data=}")
        hass_data["unsubscribe"]()
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
