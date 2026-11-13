"""Constants for the two-relay fil pilote thermostat."""

from homeassistant.components.climate import (
    PRESET_AWAY,
    PRESET_COMFORT,
    PRESET_ECO,
    PRESET_SLEEP,
)
from homeassistant.const import STATE_OFF, STATE_ON, Platform

DOMAIN = "fil_pilote_thermostat"
PLATFORMS = [Platform.CLIMATE]
DEFAULT_NAME = "Fil Pilote Thermostat"
CONF_HEATER_S1 = "heater_s1"
CONF_HEATER_S2 = "heater_s2"
CONF_SENSOR = "target_sensor"
CONF_MIN_TEMP = "min_temp"
CONF_MAX_TEMP = "max_temp"
CONF_TARGET_TEMP = "target_temp"
CONF_COLD_TOLERANCE = "cold_tolerance"
CONF_HOT_TOLERANCE = "hot_tolerance"
CONF_INITIAL_HVAC_MODE = "initial_hvac_mode"
CONF_INITIAL_PRESET = "initial_preset"
CONF_PRECISION = "precision"
CONF_SENSOR_TIMEOUT = "sensor_timeout"
DEFAULT_TOLERANCE = 0.3

# Preserve the original wiring convention. S1 and S2 are NOT interchangeable.
PILOT_STATES = {
    PRESET_COMFORT: (STATE_OFF, STATE_OFF),
    PRESET_ECO: (STATE_ON, STATE_ON),
    PRESET_AWAY: (STATE_ON, STATE_OFF),
    PRESET_SLEEP: (STATE_OFF, STATE_ON),
}
PRESETS = list(PILOT_STATES)
