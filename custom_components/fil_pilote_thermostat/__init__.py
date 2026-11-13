"""Fil pilote thermostat integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, PLATFORMS

CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a thermostat from the UI."""
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_options))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Remove entities and their listeners."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply options without a Home Assistant restart."""
    await hass.config_entries.async_reload(entry.entry_id)
