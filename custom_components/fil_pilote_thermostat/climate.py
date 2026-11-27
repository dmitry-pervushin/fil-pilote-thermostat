"""Event-driven thermostat for a two-relay fil pilote interface."""

import asyncio
import logging
import math
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import probatio as vol
from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ATTR_PRESET_MODE,
    PRESET_AWAY,
    PRESET_COMFORT,
    PRESET_ECO,
    PRESET_SLEEP,
    ClimateEntityFeature,
    ClimateExtraStoredData,
    HVACAction,
    HVACMode,
    RestoreClimate,
)
from homeassistant.components.climate import (
    PLATFORM_SCHEMA as CLIMATE_PLATFORM_SCHEMA,
)
from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_TEMPERATURE,
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_NAME,
    CONF_UNIQUE_ID,
    EVENT_HOMEASSISTANT_STARTED,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    UnitOfTemperature,
)
from homeassistant.core import CoreState
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.reload import async_setup_reload_service
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import TemperatureConverter

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
    DOMAIN,
    PILOT_STATES,
    PLATFORMS,
    PRESETS,
)
from .schema import CONFIG_FIELDS, CONFIG_SCHEMA, finite_float, validate_config

_LOGGER = logging.getLogger(__name__)
PLATFORM_SCHEMA = vol.All(
    CLIMATE_PLATFORM_SCHEMA.extend(CONFIG_FIELDS), validate_config
)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Import legacy YAML once; the config entry owns the entity afterwards."""
    await async_setup_reload_service(hass, DOMAIN, PLATFORMS)
    # Do not await entry setup from inside climate platform setup: forwarding the
    # new entry back to climate must wait for this platform to finish first.
    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_IMPORT},
            data={key: value for key, value in config.items() if key in CONFIG_FIELDS},
        ),
        "Import fil pilote YAML configuration",
    )


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up a UI-configured thermostat with a stable entity registry ID."""
    config = CONFIG_SCHEMA({**entry.data, **entry.options})
    # Retaining a legacy unique ID also retains the entity registry record,
    # including a renamed entity_id, area, and user customizations.
    entry.runtime_data = FilPiloteThermostat(
        config, entry.data.get(CONF_UNIQUE_ID, entry.entry_id)
    )
    async_add_entities([entry.runtime_data])


@dataclass(kw_only=True)
class FilPiloteStoredData(ClimateExtraStoredData):
    """Persist the requested mode even when HA stores an unavailable state."""

    requested_hvac_mode: str
    requested_preset_mode: str


class FilPiloteThermostat(RestoreClimate):
    """Control the pilot signal; the radiator still has its own thermostat."""

    _attr_should_poll = False
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
    _attr_preset_modes = PRESETS
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(self, config: dict[str, Any], unique_id: str | None = None):
        """Initialize configuration without doing I/O."""
        self._config = config
        self._attr_name = config[CONF_NAME]
        self._attr_unique_id = unique_id
        self._attr_min_temp = config[CONF_MIN_TEMP]
        self._attr_max_temp = config[CONF_MAX_TEMP]
        self._attr_precision = config[CONF_PRECISION]
        self._attr_target_temperature_step = config[CONF_PRECISION]
        self._attr_native_target_temperature = config.get(CONF_TARGET_TEMP)
        self._attr_hvac_mode = config.get(CONF_INITIAL_HVAC_MODE)
        self._attr_preset_mode = config.get(CONF_INITIAL_PRESET)
        self._relays = (config[CONF_HEATER_S1], config[CONF_HEATER_S2])
        self._sensor = config[CONF_SENSOR]
        self._lock = asyncio.Lock()
        self._ready = False
        self._heating = False
        self._command_failed = False
        self._desired_pilot = PRESET_SLEEP

    async def async_added_to_hass(self):
        """Restore state, subscribe, then reconcile even when HA is already running."""
        await super().async_added_to_hass()
        old = await self.async_get_last_state()
        extra = await self.async_get_last_extra_data()
        stored = extra.as_dict() if extra else {}
        if self._attr_native_target_temperature is None:
            restored = await self.async_get_last_climate_data(validate_range=True)
            self._attr_native_target_temperature = (
                restored.native_target_temperature if restored else None
            )
        if self._attr_native_target_temperature is None:
            self._attr_native_target_temperature = min(
                max(20, self.min_temp), self.max_temp
            )
        if self._attr_hvac_mode is None:
            restored_mode = stored.get(
                "requested_hvac_mode", old.state if old else None
            )
            self._attr_hvac_mode = (
                HVACMode(restored_mode)
                if restored_mode in self.hvac_modes
                else HVACMode.OFF
            )
        if self._attr_preset_mode is None:
            preset = stored.get(
                "requested_preset_mode",
                old.attributes.get(ATTR_PRESET_MODE) if old else None,
            )
            # Retain the original default, frost protection, on first installation.
            self._attr_preset_mode = preset if preset in PRESETS else PRESET_AWAY
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._sensor, *self._relays], self._async_state_changed
            )
        )
        # Retry failed commands, detect a stale sensor, and reconcile relay drift.
        self.async_on_remove(
            async_track_time_interval(
                self.hass, self._async_reconcile, timedelta(seconds=60)
            )
        )
        if self.hass.state is CoreState.running:
            await self._async_start()
        else:
            self.async_on_remove(
                self.hass.bus.async_listen_once(
                    EVENT_HOMEASSISTANT_STARTED, self._async_start
                )
            )

    async def _async_start(self, _event=None):
        """Wait for HA's startup before calling dependent entity services."""
        self._ready = True
        self._heating = self._observed_pilot in (PRESET_COMFORT, PRESET_ECO)
        await self._async_reconcile()

    @property
    def extra_restore_state_data(self):
        """Store native temperatures together with independent requested modes."""
        return FilPiloteStoredData(
            **super().extra_restore_state_data.as_dict(),
            requested_hvac_mode=self.hvac_mode,
            requested_preset_mode=self.preset_mode,
        )

    @property
    def available(self):
        """Never present missing input or failed output as a working thermostat."""
        return (
            self._ready
            and self._inputs_available
            and not self._command_failed
            and self._observed_pilot == self._desired_pilot
        )

    @property
    def _inputs_available(self):
        return self.native_current_temperature is not None and all(
            (state := self.hass.states.get(entity_id)) is not None
            and state.state in (STATE_ON, STATE_OFF)
            for entity_id in self._relays
        )

    @property
    def native_current_temperature(self):
        """Read a finite, fresh sensor value, converting its unit to Celsius."""
        state = self.hass.states.get(self._sensor)
        if state is None:
            return None
        timeout = self._config[CONF_SENSOR_TIMEOUT]
        if (
            timeout
            and (dt_util.utcnow() - state.last_reported).total_seconds() > timeout
        ):
            return None
        try:
            value = float(state.state)
            unit = state.attributes.get(
                ATTR_UNIT_OF_MEASUREMENT, UnitOfTemperature.CELSIUS
            )
            value = TemperatureConverter.convert(
                value, unit, self.native_temperature_unit
            )
        except TypeError, ValueError, HomeAssistantError:
            return None
        return value if math.isfinite(value) else None

    @property
    def hvac_action(self):
        """Report the observed pilot command, not measured power consumption."""
        if not self.available:
            return None
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        # Frost protection uses the radiator's internal thermostat.
        return (
            HVACAction.HEATING
            if self._observed_pilot in (PRESET_COMFORT, PRESET_ECO)
            else HVACAction.IDLE
        )

    @property
    def _observed_pilot(self):
        states = tuple(
            state.state if (state := self.hass.states.get(entity_id)) else None
            for entity_id in self._relays
        )
        return next(
            (preset for preset, pair in PILOT_STATES.items() if pair == states), None
        )

    @property
    def extra_state_attributes(self):
        """Expose useful signal diagnostics without pretending to measure heat."""
        return {
            "pilot_mode": self._observed_pilot,
            "requested_pilot_mode": self._desired_pilot,
            "requested_hvac_mode": self.hvac_mode,
            "requested_preset_mode": self.preset_mode,
            "sensor_entity_id": self._sensor,
            "heater_s1": self._relays[0],
            "heater_s2": self._relays[1],
            "command_failed": self._command_failed,
        }

    async def async_set_hvac_mode(self, hvac_mode):
        """Enable regulation or send the stop signal regardless of sensor state."""
        if hvac_mode not in self.hvac_modes:
            raise ServiceValidationError(f"Unsupported HVAC mode: {hvac_mode}")
        self._attr_hvac_mode = HVACMode(hvac_mode)
        await self._async_reconcile()

    async def async_turn_on(self):
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self):
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_set_preset_mode(self, preset_mode):
        """Change the pilot mode without implicitly enabling the thermostat."""
        if preset_mode not in PRESETS:
            raise ServiceValidationError(f"Unsupported preset: {preset_mode}")
        self._attr_preset_mode = preset_mode
        await self._async_reconcile()

    async def async_set_temperature(self, **kwargs):
        """Set a finite target and optionally change HVAC mode in the same call."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        mode = kwargs.get(ATTR_HVAC_MODE)
        if mode is not None and mode not in self.hvac_modes:
            raise ServiceValidationError(f"Unsupported HVAC mode: {mode}")
        if temperature is not None:
            try:
                temperature = finite_float(temperature)
            except vol.Invalid as err:
                raise ServiceValidationError(str(err)) from err
            if not self.min_temp <= temperature <= self.max_temp:
                raise ServiceValidationError(
                    "Target temperature is outside the configured range"
                )
            self._attr_native_target_temperature = temperature
        if mode is not None:
            self._attr_hvac_mode = HVACMode(mode)
        await self._async_reconcile()

    async def _async_state_changed(self, _event):
        await self._async_reconcile()

    async def _async_reconcile(self, _now=None):
        """Serialize all control paths; maintain hysteresis inside the dead band."""
        if not self._ready:
            return
        async with self._lock:
            if self.hvac_mode == HVACMode.OFF or not self._inputs_available:
                self._heating = False
                desired = PRESET_SLEEP
            elif self.preset_mode in (PRESET_AWAY, PRESET_SLEEP):
                self._heating = False
                desired = self.preset_mode
            else:
                temperature = self.native_current_temperature
                target = self.native_target_temperature
                if temperature <= target - self._config[CONF_COLD_TOLERANCE]:
                    self._heating = True
                elif temperature >= target + self._config[CONF_HOT_TOLERANCE]:
                    self._heating = False
                desired = self.preset_mode if self._heating else PRESET_SLEEP
            self._desired_pilot = desired
            await self._async_set_pilot(desired)
            self.async_write_ha_state()

    async def _async_set_pilot(self, preset):
        """Apply only changed outputs, waiting for services and attempting both relays."""
        failed = False
        # Turn ON before OFF when changing polarity: the intermediate state is eco
        # rather than comfort (both relays off). This is not an electrical interlock.
        changes = sorted(
            zip(self._relays, PILOT_STATES[preset], strict=True),
            key=lambda pair: pair[1] != STATE_ON,
        )
        for entity_id, desired in changes:
            state = self.hass.states.get(entity_id)
            if state is None or state.state not in (STATE_ON, STATE_OFF):
                failed = True
                continue
            if state.state == desired:
                continue
            try:
                await self.hass.services.async_call(
                    entity_id.split(".", 1)[0],
                    SERVICE_TURN_ON if desired == STATE_ON else SERVICE_TURN_OFF,
                    {ATTR_ENTITY_ID: entity_id},
                    blocking=True,
                    context=self._context,
                )
            except HomeAssistantError as err:
                failed = True
                if not self._command_failed:
                    _LOGGER.error("Cannot set %s to %s: %s", entity_id, desired, err)
        self._command_failed = failed
