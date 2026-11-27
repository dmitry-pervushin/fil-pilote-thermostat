"""Shared validation for YAML, UI configuration, and options."""

import math

import probatio as vol
from homeassistant.components.climate import HVACMode
from homeassistant.const import CONF_NAME, CONF_UNIQUE_ID
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_COLD_TOLERANCE,
    CONF_HEATER_S1,
    CONF_HEATER_S2,
    CONF_HOT_TOLERANCE,
    CONF_INITIAL_HVAC_MODE,
    CONF_INITIAL_PRESET,
    CONF_MAX_TEMP,
    CONF_MIN_TEMP,
    CONF_PRECISION,
    CONF_SENSOR,
    CONF_SENSOR_TIMEOUT,
    CONF_TARGET_TEMP,
    DEFAULT_NAME,
    DEFAULT_TOLERANCE,
    PRESETS,
)


def finite_float(value):
    """Reject NaN and infinities as well as non-numeric input."""
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as err:
        raise vol.Invalid("Expected a finite number") from err
    if not math.isfinite(result):
        raise vol.Invalid("Expected a finite number")
    return result


def actuator(value):
    """Allow entities with reliable on/off semantics."""
    value = cv.entity_id(value)
    if value.split(".", 1)[0] not in ("switch", "light", "input_boolean"):
        raise vol.Invalid("Use a switch, light, or input_boolean")
    return value


CONFIG_FIELDS = {
    vol.Required(CONF_HEATER_S1): actuator,
    vol.Required(CONF_HEATER_S2): actuator,
    vol.Required(CONF_SENSOR): cv.entity_domain("sensor"),
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): vol.All(
        cv.string, vol.Length(min=1)
    ),
    vol.Optional(CONF_UNIQUE_ID): cv.string,
    vol.Optional(CONF_MIN_TEMP, default=7): finite_float,
    vol.Optional(CONF_MAX_TEMP, default=35): finite_float,
    vol.Optional(CONF_TARGET_TEMP): finite_float,
    vol.Optional(CONF_COLD_TOLERANCE, default=DEFAULT_TOLERANCE): vol.All(
        finite_float, vol.Range(min=0)
    ),
    vol.Optional(CONF_HOT_TOLERANCE, default=DEFAULT_TOLERANCE): vol.All(
        finite_float, vol.Range(min=0)
    ),
    vol.Optional(CONF_INITIAL_HVAC_MODE): vol.In([HVACMode.HEAT, HVACMode.OFF]),
    vol.Optional(CONF_INITIAL_PRESET): vol.In(PRESETS),
    vol.Optional(CONF_PRECISION, default=0.1): vol.All(
        finite_float, vol.In([0.1, 0.5, 1.0])
    ),
    vol.Optional(CONF_SENSOR_TIMEOUT, default=0): vol.All(
        finite_float, vol.Range(min=0)
    ),
}


def validate_config(config):
    """Validate relationships between fields. All configured temperatures are °C."""
    if config[CONF_HEATER_S1] == config[CONF_HEATER_S2]:
        raise vol.Invalid("Relays S1 and S2 must be different")
    if config[CONF_MIN_TEMP] >= config[CONF_MAX_TEMP]:
        raise vol.Invalid("Minimum temperature must be less than maximum")
    if CONF_TARGET_TEMP in config and not (
        config[CONF_MIN_TEMP] <= config[CONF_TARGET_TEMP] <= config[CONF_MAX_TEMP]
    ):
        raise vol.Invalid("Target temperature is outside the configured range")
    if config[CONF_COLD_TOLERANCE] == config[CONF_HOT_TOLERANCE] == 0:
        raise vol.Invalid("At least one tolerance must be greater than zero")
    return config


CONFIG_SCHEMA = vol.All(vol.Schema(CONFIG_FIELDS), validate_config)
