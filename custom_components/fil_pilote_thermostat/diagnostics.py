"""Diagnostic export, including requested modes while the entity is unavailable."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry):
    """Export configuration and current control state; this integration has no secrets."""
    entity = entry.runtime_data
    return {
        "configuration": {**entry.data, **entry.options},
        "available": entity.available,
        "current_temperature": entity.native_current_temperature,
        "target_temperature": entity.native_target_temperature,
        **entity.extra_state_attributes,
    }
