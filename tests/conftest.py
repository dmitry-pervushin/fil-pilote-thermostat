"""Test against real HA Core with in-memory relay services."""

from pathlib import Path

import pytest
from homeassistant import loader
from homeassistant.bootstrap import async_load_base_functionality
from homeassistant.config_entries import ConfigEntries
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import async_setup_component


@pytest.fixture
async def hass(tmp_path):
    (tmp_path / "custom_components").symlink_to(
        Path(__file__).resolve().parents[1] / "custom_components",
        target_is_directory=True,
    )
    instance = HomeAssistant(str(tmp_path))
    loader.async_setup(instance)
    instance.config_entries = ConfigEntries(instance, {})
    assert await async_load_base_functionality(instance)
    instance.config.skip_pip = True
    assert await async_setup_component(instance, "homeassistant", {})
    calls = []

    async def relay_service(call):
        calls.append((call.data["entity_id"], call.service))
        if instance.data.get("test_fail_relays"):
            raise HomeAssistantError("relay disconnected")
        instance.states.async_set(
            call.data["entity_id"], "on" if call.service == "turn_on" else "off"
        )

    for domain in ("switch", "light", "input_boolean"):
        for service in ("turn_on", "turn_off"):
            instance.services.async_register(domain, service, relay_service)
    instance.data["test_relay_calls"] = calls
    instance.states.async_set("switch.s1", "off")
    instance.states.async_set("switch.s2", "on")
    instance.states.async_set("sensor.room", "19", {"unit_of_measurement": "°C"})
    yield instance
    await instance.async_stop(force=True)
    await instance.async_block_till_done()
    instance.import_executor.shutdown(wait=True)


@pytest.fixture
def config():
    return {
        "platform": "fil_pilote_thermostat",
        "name": "Room",
        "unique_id": "room",
        "heater_s1": "switch.s1",
        "heater_s2": "switch.s2",
        "target_sensor": "sensor.room",
        "target_temp": 20,
        "initial_hvac_mode": "heat",
        "initial_preset": "comfort",
    }
