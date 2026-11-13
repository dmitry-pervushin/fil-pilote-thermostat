"""UI setup and editable thermostat options."""

import logging

import probatio as vol
from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.const import CONF_NAME, CONF_UNIQUE_ID
from homeassistant.core import callback
from homeassistant.helpers import selector

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
    DOMAIN,
    PRESETS,
)
from .schema import CONFIG_SCHEMA

_LOGGER = logging.getLogger(__name__)


def _entity_selector(domains):
    return selector.EntitySelector(selector.EntitySelectorConfig(domain=domains))


def _settings_schema(values):
    """Use explicit units; HA converts climate display and service temperatures."""
    fields = {}
    for key, default, minimum, unit in (
        (CONF_MIN_TEMP, 7, None, "°C"),
        (CONF_MAX_TEMP, 35, None, "°C"),
        (CONF_TARGET_TEMP, None, None, "°C"),
        (CONF_COLD_TOLERANCE, DEFAULT_TOLERANCE, 0, "°C"),
        (CONF_HOT_TOLERANCE, DEFAULT_TOLERANCE, 0, "°C"),
        (CONF_SENSOR_TIMEOUT, 0, 0, "s"),
    ):
        field = vol.Optional(key)
        if key in values or default is not None:
            field = vol.Optional(key, default=values.get(key, default))
        settings = {"step": 0.1, "mode": "box", "unit_of_measurement": unit}
        if minimum is not None:
            settings["min"] = minimum
        fields[field] = selector.NumberSelector(
            selector.NumberSelectorConfig(**settings)
        )
    for key, options in (
        (CONF_INITIAL_HVAC_MODE, ["off", "heat"]),
        (CONF_INITIAL_PRESET, PRESETS),
    ):
        field = (
            vol.Optional(key, default=values[key])
            if key in values
            else vol.Optional(key)
        )
        fields[field] = selector.SelectSelector(
            selector.SelectSelectorConfig(options=options, translation_key=key)
        )
    fields[
        vol.Optional(
            CONF_PRECISION, default=str(float(values.get(CONF_PRECISION, 0.1)))
        )
    ] = selector.SelectSelector(
        selector.SelectSelectorConfig(options=["0.1", "0.5", "1.0"])
    )
    return vol.Schema(fields)


class FilPiloteConfigFlow(ConfigFlow, domain=DOMAIN):
    """Create one config entry per independent two-relay interface."""

    VERSION = 1

    def __init__(self):
        self._input = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return FilPiloteOptionsFlow()

    async def async_step_import(self, user_input):
        """Move YAML into a persistent entry without reapplying it on restart."""
        try:
            config = CONFIG_SCHEMA(user_input)
        except vol.Invalid as err:
            _LOGGER.error("Cannot import fil pilote YAML configuration: %s", err)
            return self.async_abort(reason="invalid_settings")

        relays = {config[CONF_HEATER_S1], config[CONF_HEATER_S2]}
        await self.async_set_unique_id("|".join(sorted(relays)))
        self._abort_if_unique_id_configured()
        for entry in self._async_current_entries():
            if relays & {entry.data[CONF_HEATER_S1], entry.data[CONF_HEATER_S2]} or (
                CONF_UNIQUE_ID in config
                and config[CONF_UNIQUE_ID] == entry.data.get(CONF_UNIQUE_ID)
            ):
                _LOGGER.error(
                    "Cannot import thermostat %s: a relay or unique ID is already used by %s",
                    config[CONF_NAME],
                    entry.title,
                )
                return self.async_abort(reason="already_configured")

        identity = {
            CONF_NAME,
            CONF_HEATER_S1,
            CONF_HEATER_S2,
            CONF_SENSOR,
            CONF_UNIQUE_ID,
        }
        _LOGGER.info(
            "Imported thermostat %s from YAML. Manage its settings in Devices & services; "
            "the old YAML block can be removed and will no longer override UI settings",
            config[CONF_NAME],
        )
        return self.async_create_entry(
            title=config[CONF_NAME],
            data={key: value for key, value in config.items() if key in identity},
            options={
                key: value for key, value in config.items() if key not in identity
            },
        )

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            s1, s2 = user_input[CONF_HEATER_S1], user_input[CONF_HEATER_S2]
            if s1 == s2:
                errors["base"] = "same_relays"
            elif any(
                {s1, s2} & {entry.data[CONF_HEATER_S1], entry.data[CONF_HEATER_S2]}
                for entry in self._async_current_entries()
            ) or any(
                {s1, s2}
                & {
                    state.attributes.get(CONF_HEATER_S1),
                    state.attributes.get(CONF_HEATER_S2),
                }
                for state in self.hass.states.async_all("climate")
            ):
                return self.async_abort(reason="already_configured")
            elif not user_input[CONF_NAME].strip():
                errors[CONF_NAME] = "empty_name"
            else:
                self._input = user_input
                await self.async_set_unique_id("|".join(sorted((s1, s2))))
                self._abort_if_unique_id_configured()
                return await self.async_step_settings()
        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_NAME): selector.TextSelector(),
                vol.Required(CONF_HEATER_S1): _entity_selector(
                    ["switch", "light", "input_boolean"]
                ),
                vol.Required(CONF_HEATER_S2): _entity_selector(
                    ["switch", "light", "input_boolean"]
                ),
                vol.Required(CONF_SENSOR): _entity_selector("sensor"),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_settings(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                config = CONFIG_SCHEMA({**self._input, **user_input})
            except vol.Invalid:
                errors["base"] = "invalid_settings"
            else:
                return self.async_create_entry(
                    title=config[CONF_NAME],
                    data=self._input,
                    options={
                        key: value
                        for key, value in config.items()
                        if key not in self._input
                    },
                )
        return self.async_show_form(
            step_id="settings",
            data_schema=_settings_schema(user_input or {}),
            errors=errors,
        )


class FilPiloteOptionsFlow(OptionsFlow):
    """Edit sensor and tuning; relay identity stays fixed."""

    async def async_step_init(self, user_input=None):
        errors = {}
        current = {**self.config_entry.data, **self.config_entry.options}
        if user_input is not None:
            try:
                config = CONFIG_SCHEMA({**self.config_entry.data, **user_input})
            except vol.Invalid:
                errors["base"] = "invalid_settings"
            else:
                return self.async_create_entry(
                    title="",
                    data={
                        key: value
                        for key, value in config.items()
                        if key not in (CONF_HEATER_S1, CONF_HEATER_S2)
                    },
                )
        values = user_input if user_input is not None else current
        fields = {
            vol.Required(
                CONF_SENSOR, default=values.get(CONF_SENSOR, current[CONF_SENSOR])
            ): _entity_selector("sensor"),
            **_settings_schema(values).schema,
        }
        return self.async_show_form(
            step_id="init", data_schema=vol.Schema(fields), errors=errors
        )
