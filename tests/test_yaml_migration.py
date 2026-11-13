"""Migrate real YAML platforms without losing entity identity or UI settings."""

import asyncio

from homeassistant.core import State
from homeassistant.helpers import area_registry, entity_registry, restore_state
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util

from custom_components.fil_pilote_thermostat.const import DOMAIN


async def import_yaml(hass, config):
    return await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "import"},
        data={key: value for key, value in config.items() if key != "platform"},
    )


async def test_yaml_without_unique_id_keeps_bureau_and_restores_state(hass, config):
    config["name"] = "Bureau"
    for key in ("unique_id", "target_temp", "initial_hvac_mode", "initial_preset"):
        config.pop(key)
    restore_state.async_get(hass).last_states_by_entity_id["climate.bureau"] = (
        restore_state.StoredState(
            State(
                "climate.bureau", "heat", {"temperature": 22, "preset_mode": "comfort"}
            ),
            None,
            dt_util.utcnow(),
        )
    )
    assert await async_setup_component(hass, "climate", {"climate": [config]})
    await hass.async_start()
    await hass.async_block_till_done()
    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.source == "import"
    registered = entity_registry.async_get(hass).async_get("climate.bureau")
    assert registered.unique_id == entry.entry_id
    assert registered.config_entry_id == entry.entry_id
    state = hass.states.get("climate.bureau")
    assert state.state == "heat"
    assert state.attributes["temperature"] == 22
    assert state.attributes["preset_mode"] == "comfort"
    assert hass.states.get("climate.bureau_2") is None

    # With no YAML callback, the imported entry can be unloaded and set up again.
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert (
        entity_registry.async_get(hass).async_get("climate.bureau").id == registered.id
    )
    assert hass.states.get("climate.bureau").attributes["temperature"] == 22


async def test_existing_unique_id_retains_registry_customizations(hass, config):
    registry = entity_registry.async_get(hass)
    old = registry.async_get_or_create(
        "climate", DOMAIN, config["unique_id"], suggested_object_id="bureau"
    )
    area = area_registry.async_get(hass).async_get_or_create("Office")
    old = registry.async_update_entity(
        old.entity_id, name="My office", icon="mdi:desk", area_id=area.id
    )
    assert await async_setup_component(hass, "climate", {"climate": [config]})
    await hass.async_start()
    await hass.async_block_till_done()
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    migrated = registry.async_get("climate.bureau")
    assert migrated.id == old.id
    assert migrated.unique_id == config["unique_id"]
    assert migrated.name == "My office"
    assert migrated.icon == "mdi:desk"
    assert migrated.area_id == area.id
    assert migrated.config_entry_id == entry.entry_id
    assert hass.states.get("climate.room") is None


async def test_leftover_yaml_does_not_override_ui_options(hass, config):
    assert await async_setup_component(hass, "climate", {"climate": [config]})
    await hass.async_start()
    await hass.async_block_till_done()
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        flow["flow_id"],
        {
            "target_sensor": "sensor.room",
            "target_temp": 24,
            "initial_hvac_mode": "heat",
            "initial_preset": "eco",
        },
    )
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    repeat = await import_yaml(hass, config)
    assert repeat["type"] == "abort"
    assert repeat["reason"] == "already_configured"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    assert entry.options["target_temp"] == 24
    assert hass.states.get("climate.room").attributes["preset_mode"] == "eco"
    assert hass.states.get("climate.room_2") is None


async def test_concurrent_imports_do_not_duplicate_controllers(hass, config):
    results = await asyncio.gather(import_yaml(hass, config), import_yaml(hass, config))
    await hass.async_block_till_done()
    assert sorted(result["type"] for result in results) == ["abort", "create_entry"]
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_import_rejects_shared_relays_and_unique_ids(hass, config):
    await import_yaml(hass, config)
    await hass.async_block_till_done()
    shared_relay = await import_yaml(
        hass,
        {**config, "name": "Other", "unique_id": "other", "heater_s2": "switch.other"},
    )
    assert shared_relay["reason"] == "already_configured"
    reused_id = await import_yaml(
        hass, {**config, "heater_s1": "switch.other1", "heater_s2": "switch.other2"}
    )
    assert reused_id["reason"] == "already_configured"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_import_rejects_invalid_yaml(hass, config):
    result = await import_yaml(hass, {**config, "target_temp": 100})
    assert result["reason"] == "invalid_settings"
    assert not hass.config_entries.async_entries(DOMAIN)
