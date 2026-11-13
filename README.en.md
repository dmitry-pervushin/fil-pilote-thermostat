<p align="center"><img src="assets/icon.svg" width="144" alt="Fil Pilote Thermostat"></p>

# Fil Pilote Thermostat

[Français](README.md) · [English](README.en.md) · [Русский](README.ru.md)

A local Home Assistant thermostat for electric radiators controlled by a **two-relay fil pilote interface** and a room temperature sensor. Configure it through the UI; existing YAML configurations are imported automatically.

Requires **Home Assistant 2026.11 or later**. Development checks run against Core 2026.11.1 and Python 3.14.

## Installation

**YAML configuration is not required.** The recommended method is Home Assistant’s UI: select your relays and sensor, then adjust the settings without editing `configuration.yaml`.

1. Copy `custom_components/fil_pilote_thermostat` from this project into your HA configuration directory, keeping the same path: `/config/custom_components/fil_pilote_thermostat/`.
2. Restart Home Assistant.
3. Open **Settings → Devices & services → Add integration → Fil Pilote Thermostat**.
4. Select the two relay entities and your room sensor, then set your temperature limits and tolerances.

Relays can be `switch`, `light`, or `input_boolean` entities with on/off semantics. The sensor must be a `sensor` entity. Options can be changed without restarting HA. Relay identities stay fixed; recreate the entry to change them. A relay cannot be shared by multiple UI-configured thermostats.

The project is available on [GitHub](https://github.com/dmitry-pervushin/fil-pilote-thermostat). To add it in HACS, open **Custom repositories**, enter this repository URL, and choose the **Integration** category. The project is not listed in the default HACS catalog.

## Pilot signals and presets

The original relay convention is preserved:

| Preset | Radiator command | S1 | S2 |
| --- | --- | --- | --- |
| `comfort` | Comfort | off | off |
| `eco` | Eco | on | on |
| `away` | Frost protection / Hors-gel | on | off |
| `sleep` | Stop / Arrêt | off | on |

**S1 and S2 are not interchangeable.** Check the mapping against your existing pilot-wire interface before enabling heating. These are logical relay states, not instructions for connecting mains wiring. The component expects an already installed, appropriate fil pilote interface.

In HVAC `heat`, Comfort and Eco use the external temperature sensor with hysteresis. Heating starts at `target − cold_tolerance` and stops at `target + hot_tolerance`; the previous demand is retained inside the band. Eco sends the radiator's Eco command, so the radiator may apply its own temperature reduction.

Away sends frost protection continuously; the radiator controls its own frost threshold. Sleep sends stop continuously. HVAC `off` always sends stop, regardless of the selected preset or sensor availability. Selecting a preset does not turn heating on. On a new installation the defaults are **Off**, **Away**, and a **20 °C** target, clamped to your configured limits.

The radiator must be in its external/program/pilot-wire mode, and its local thermostat must allow the intended temperature. A pilot command cannot override its internal temperature limit. `hvac_action: heating` means a Comfort/Eco signal is observed; it does not measure electrical power or prove that the heating element is active.

## Temperatures and restoration

All configuration values, including tolerances, use **°C**. HA converts climate display values and standard service calls to your system's preferred units. Sensor values in °C, °F, or K are converted to °C; a sensor without a unit is interpreted as °C.

The target, HVAC mode, and preset are restored after a restart or reload. Optional `target_temp`, `initial_hvac_mode`, and `initial_preset` override their restored values **at every startup/reload**. Leave them blank to retain the user's latest settings. Invalid restored modes are ignored, and invalid/out-of-range targets fall back to a valid default.

## Fault handling

Missing, unavailable, non-numeric, NaN, or infinite sensor readings make the thermostat unavailable and request the stop signal. A missing relay does the same; the component still attempts the stop combination on any reachable relay. With a missing or failed relay, delivery of the complete stop signal cannot be guaranteed.

`sensor_timeout` optionally rejects readings that have not been reported for the configured number of seconds. It defaults to `0` (disabled), which suits sensors that report only when their value changes. Freshness is checked on state changes and every 60 seconds, so expiration can take up to one additional minute to detect.

Commands wait for their services to finish, avoid redundant calls, serialize concurrent changes, and retry/reconcile every 60 seconds. Relay changes also trigger reconciliation: control belongs to the climate entity, so manual changes to the underlying relays are corrected. A service error marks the thermostat unavailable until a successful reconciliation. Unloading removes listeners and timers; it leaves the last physical pilot signal unchanged.

Useful state attributes: `pilot_mode`, `requested_pilot_mode`, `requested_hvac_mode`, `requested_preset_mode`, `heater_s1`, `heater_s2`, `sensor_entity_id`, `command_failed`. HA hides state attributes while an entity is unavailable; the integration's diagnostic download remains available during faults.

## YAML (optional)

If you added the thermostat through the UI, skip this section: no YAML block is needed.

**Since version 1.1.0, YAML → UI migration is automatic.** Update the component, keep your YAML block in place, and restart HA. Each thermostat is imported into **Settings → Devices & services**, where its options can then be managed.

A missing `unique_id` is assigned automatically, removing the warning about entity settings being unavailable. An existing unique ID and its entity registry record are retained, including a customized name, area, and icon. Without a previous unique ID, the YAML name still determines the entity ID; for example, `name: Bureau` yields `climate.bureau` when that ID is free. Previously saved target and mode are restored unless YAML startup overrides replace them.

After checking the integration and entity ID, **you can remove the thermostat's YAML block**. The component does not edit your files. Leaving the block in place creates no duplicates on subsequent startups and does not overwrite options changed in the UI: **YAML is read only for the initial import**. If the same relays already belong to a configured thermostat, that entry is kept without importing another one. Do not manually add a second integration before migration.

If your previous YAML used °F, convert targets, limits, and tolerances to °C before upgrading. The new configuration format always uses °C.

```yaml
climate:
  - platform: fil_pilote_thermostat
    name: Living room
    unique_id: living_room_fil_pilote
    heater_s1: switch.radiator_s1
    heater_s2: switch.radiator_s2
    target_sensor: sensor.living_room_temperature
    min_temp: 7
    max_temp: 30
    cold_tolerance: 0.3
    hot_tolerance: 0.3
    precision: 0.1
    sensor_timeout: 0
    # Optional: override restored settings at every startup/reload.
    # target_temp: 20
    # initial_hvac_mode: heat
    # initial_preset: comfort
```

| Option | Default | Meaning |
| --- | --- | --- |
| `heater_s1`, `heater_s2` | required | Two distinct relay entities |
| `target_sensor` | required | Room temperature sensor |
| `name` | Fil Pilote Thermostat | Entity name |
| `unique_id` | optional | Existing ID retained; assigned automatically if omitted |
| `min_temp`, `max_temp` | 7 / 35 | Target limits in °C; minimum must be less than maximum |
| `cold_tolerance`, `hot_tolerance` | 0.3 / 0.3 | Hysteresis in °C; non-negative, at least one greater than zero |
| `precision` | 0.1 | Display precision and target step: 0.1, 0.5, or 1 |
| `sensor_timeout` | 0 | Maximum age since last sensor report, in seconds; 0 disables |
| `target_temp` | restored / 20 | Startup target in °C |
| `initial_hvac_mode` | restored / off | `heat` or `off` |
| `initial_preset` | restored / away | `comfort`, `eco`, `away`, or `sleep` |

## Development

```sh
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/pytest -q
```

Tests run against real HA Core, using in-memory sensor states and relay services. They do not operate physical radiators. The original SVG in `assets/icon.svg` is also provided as light/dark PNG brand icons inside the integration, following [HA's local brand-image format](https://contributors.home-assistant.io/blog/2026/02/24/brands-proxy-api/).
