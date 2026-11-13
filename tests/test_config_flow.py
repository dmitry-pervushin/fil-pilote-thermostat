"""Validate the complete UI lifecycle against the real config entry manager."""

import probatio as vol
import pytest
from homeassistant.helpers import entity_registry as er

from custom_components.fil_pilote_thermostat.schema import CONFIG_SCHEMA

DOMAIN = "fil_pilote_thermostat"
USER = {
    "name": "Room",
    "heater_s1": "switch.s1",
    "heater_s2": "switch.s2",
    "target_sensor": "sensor.room",
}


async def create_entry(hass, settings=None):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER)
    assert result["step_id"] == "settings"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], settings or {}
    )
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    return result["result"]


async def test_config_entry_options_reload_and_unload(hass):
    await hass.async_start()
    entry = await create_entry(
        hass,
        {"initial_hvac_mode": "heat", "initial_preset": "comfort", "target_temp": 21},
    )
    state = hass.states.get("climate.room")
    assert state.state == "heat"
    assert state.attributes["temperature"] == 21
    registry = er.async_get(hass)
    assert registry.async_get("climate.room").unique_id == entry.entry_id
    options = await hass.config_entries.options.async_init(entry.entry_id)
    assert options["step_id"] == "init"
    options = await hass.config_entries.options.async_configure(
        options["flow_id"],
        {
            "target_sensor": "sensor.room",
            "min_temp": 10,
            "max_temp": 30,
            "target_temp": 23,
            "initial_hvac_mode": "heat",
            "initial_preset": "eco",
        },
    )
    assert options["type"] == "create_entry"
    await hass.async_block_till_done()
    assert hass.states.get("climate.room").attributes["temperature"] == 23
    assert hass.states.get("climate.room").attributes["preset_mode"] == "eco"
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    calls = len(hass.data["test_relay_calls"])
    hass.states.async_set("sensor.room", "29", {"unit_of_measurement": "°C"})
    await hass.async_block_till_done()
    assert len(hass.data["test_relay_calls"]) == calls


async def test_duplicate_and_shared_relays_rejected(hass):
    await create_entry(hass)
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {**USER, "heater_s2": "switch.other"}
    )
    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"


async def test_same_relays_and_invalid_range_show_errors(hass):
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {**USER, "heater_s2": "switch.s1"}
    )
    assert result["errors"] == {"base": "same_relays"}
    result = await hass.config_entries.flow.async_configure(flow["flow_id"], USER)
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"min_temp": 30, "max_temp": 10}
    )
    assert result["errors"] == {"base": "invalid_settings"}


@pytest.mark.parametrize(
    "overrides",
    [
        {"min_temp": 30, "max_temp": 10},
        {"target_temp": 100},
        {"cold_tolerance": -1},
        {"hot_tolerance": -1},
        {"cold_tolerance": 0, "hot_tolerance": 0},
        {"target_temp": "nan"},
        {"min_temp": "inf"},
        {"sensor_timeout": -1},
        {"heater_s2": "switch.s1"},
        {"heater_s1": "climate.other"},
    ],
)
def test_invalid_yaml(overrides):
    with pytest.raises(vol.Invalid):
        CONFIG_SCHEMA({**USER, **overrides})
