"""Exercise actual climate services, startup, hysteresis, and fault handling."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from homeassistant.core import State
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import restore_state
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util


async def setup_thermostat(hass, config, *, start=True):
    assert await async_setup_component(hass, "climate", {"climate": [config]})
    await hass.async_block_till_done()
    if start:
        await hass.async_start()
        await hass.async_block_till_done()
    return hass.data["climate"].get_entity("climate.room")


async def set_temperature(hass, value):
    hass.states.async_set("sensor.room", str(value), {"unit_of_measurement": "°C"})
    await hass.async_block_till_done()


async def climate_call(hass, service, **data):
    await hass.services.async_call(
        "climate", service, {"entity_id": "climate.room", **data}, blocking=True
    )
    await hass.async_block_till_done()


async def test_startup_and_hysteresis(hass, config):
    await setup_thermostat(hass, config)
    assert hass.states.get("switch.s2").state == "off"
    assert hass.states.get("climate.room").attributes["hvac_action"] == "heating"
    calls = len(hass.data["test_relay_calls"])
    await set_temperature(hass, 20.1)
    assert hass.states.get("switch.s2").state == "off"
    assert len(hass.data["test_relay_calls"]) == calls
    await set_temperature(hass, 20.3)
    assert hass.states.get("switch.s2").state == "on"
    await set_temperature(hass, 19.9)
    assert hass.states.get("switch.s2").state == "on"
    await set_temperature(hass, 19.7)
    assert hass.states.get("switch.s2").state == "off"


async def test_setup_when_already_running(hass, config):
    await hass.async_start()
    await setup_thermostat(hass, config, start=False)
    assert hass.states.get("switch.s2").state == "off"


async def test_stop_without_sensor_at_startup(hass, config):
    hass.states.async_set("sensor.room", "unavailable")
    hass.states.async_set("switch.s2", "off")
    config["initial_hvac_mode"] = "off"
    await setup_thermostat(hass, config)
    assert hass.states.get("switch.s2").state == "on"
    assert hass.states.get("climate.room").state == "unavailable"


@pytest.mark.parametrize(
    "bad", ["unavailable", "unknown", "oops", "nan", "inf", "-inf", None]
)
async def test_invalid_sensor_stops_and_recovers(hass, config, bad):
    await setup_thermostat(hass, config)
    if bad is None:
        hass.states.async_remove("sensor.room")
    else:
        hass.states.async_set("sensor.room", bad)
    await hass.async_block_till_done()
    assert hass.states.get("switch.s2").state == "on"
    assert hass.states.get("climate.room").state == "unavailable"
    assert hass.states.get("climate.room").attributes.get("current_temperature") is None
    await set_temperature(hass, 18)
    assert hass.states.get("climate.room").state == "heat"
    assert hass.states.get("switch.s2").state == "off"


async def test_presets_and_combined_temperature_service(hass, config):
    await setup_thermostat(hass, config)
    for preset, expected in (
        ("eco", ("on", "on")),
        ("away", ("on", "off")),
        ("sleep", ("off", "on")),
        ("comfort", ("off", "off")),
    ):
        await climate_call(hass, "set_preset_mode", preset_mode=preset)
        assert (
            tuple(hass.states.get(e).state for e in ("switch.s1", "switch.s2"))
            == expected
        )
    await climate_call(hass, "turn_off")
    assert hass.states.get("climate.room").state == "off"
    assert hass.states.get("switch.s2").state == "on"
    await climate_call(hass, "set_temperature", temperature=22, hvac_mode="heat")
    assert hass.states.get("switch.s2").state == "off"
    assert hass.states.get("climate.room").attributes["temperature"] == 22


async def test_relay_loss_recovery_and_external_drift(hass, config):
    await setup_thermostat(hass, config)
    hass.states.async_set("switch.s1", "unavailable")
    await hass.async_block_till_done()
    assert hass.states.get("switch.s2").state == "on"
    assert hass.states.get("climate.room").state == "unavailable"
    hass.states.async_set("switch.s1", "off")
    await hass.async_block_till_done()
    assert hass.states.get("switch.s2").state == "off"
    hass.states.async_set("switch.s2", "on")
    await hass.async_block_till_done()
    assert hass.states.get("switch.s2").state == "off"


async def test_service_failure_is_visible_and_retry_recovers(hass, config):
    await setup_thermostat(hass, config)
    entity = hass.data["climate"].get_entity("climate.room")
    hass.data["test_fail_relays"] = True
    await entity.async_turn_off()
    assert hass.states.get("climate.room").state == "unavailable"
    assert entity.extra_state_attributes["command_failed"]
    hass.data["test_fail_relays"] = False
    await entity._async_reconcile()
    await hass.async_block_till_done()
    assert hass.states.get("climate.room").state == "off"
    assert hass.states.get("switch.s2").state == "on"


async def test_sensor_units_and_timeout(hass, config):
    config["sensor_timeout"] = 300
    hass.states.async_set("sensor.room", "68", {"unit_of_measurement": "°F"})
    entity = await setup_thermostat(hass, config)
    assert hass.states.get("climate.room").attributes["current_temperature"] == 20
    with patch(
        "custom_components.fil_pilote_thermostat.climate.dt_util.utcnow",
        return_value=dt_util.utcnow() + timedelta(seconds=301),
    ):
        await entity._async_reconcile()
        assert not entity.available
        assert hass.states.get("switch.s2").state == "on"


@pytest.mark.parametrize("temperature", [float("nan"), float("inf"), 100, -100])
async def test_invalid_targets_rejected(hass, config, temperature):
    entity = await setup_thermostat(hass, config)
    with pytest.raises(ServiceValidationError):
        await entity.async_set_temperature(temperature=temperature)
    assert entity.native_target_temperature == 20


@pytest.mark.parametrize("old_state", ["heat", "unavailable"])
async def test_restore_requested_state_even_after_failure(hass, config, old_state):
    from custom_components.fil_pilote_thermostat.climate import FilPiloteStoredData

    for key in ("target_temp", "initial_hvac_mode", "initial_preset"):
        config.pop(key)
    extra = FilPiloteStoredData(
        native_temperature_unit="°C",
        native_current_temperature=19,
        native_target_temperature=22,
        native_target_temperature_high=None,
        native_target_temperature_low=None,
        requested_hvac_mode="heat",
        requested_preset_mode="eco",
    )
    restore_state.async_get(hass).last_states_by_entity_id["climate.room"] = (
        restore_state.StoredState(
            State("climate.room", old_state), extra, dt_util.utcnow()
        )
    )
    entity = await setup_thermostat(hass, config)
    assert entity.hvac_mode == "heat"
    assert entity.preset_mode == "eco"
    assert entity.native_target_temperature == 22
    assert hass.states.get("switch.s1").state == "on"
    assert hass.states.get("switch.s2").state == "on"


async def test_restore_legacy_state(hass, config):
    for key in ("target_temp", "initial_hvac_mode", "initial_preset"):
        config.pop(key)
    restore_state.async_get(hass).last_states_by_entity_id["climate.room"] = (
        restore_state.StoredState(
            State(
                "climate.room", "heat", {"temperature": 23, "preset_mode": "comfort"}
            ),
            None,
            dt_util.utcnow(),
        )
    )
    entity = await setup_thermostat(hass, config)
    assert entity.native_target_temperature == 23
    assert entity.hvac_mode == "heat"
    assert entity.preset_mode == "comfort"
