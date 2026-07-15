# Energy Dispatcher

A Home Assistant custom integration that acts as an **energy decision engine** for controllable loads.

It answers one question per load:

> *Should this load run now, and with which energy source?*

Your automations handle the physical device — setpoints, modes, and control logic stay in YAML.

```
energy_dispatcher.dehumidifier
  state: ON
  energy_mode: SOLAR
```

```yaml
# Your automation reacts to the decision
action:
  - choose:
      - conditions:
          - condition: template
            value_template: "{{ state_attr('energy_dispatcher.dehumidifier', 'energy_mode') == 'SOLAR' }}"
        sequence:
          - action: humidifier.set_humidity
            data:
              humidity: 50
```

## Features

- **Grid export detection** — prefer self-consumption when exporting to the grid
- **Spot price evaluation** — generic price sensor, full timeline (today + tomorrow)
- **Per-load rules** — allowed energy sources, required power, minimum runtime
- **Runtime scheduling** — fulfil daily/weekly minute quotas on the cheapest allowed hours
- **Power guard** — optional hourly import limit (kWh) with WARNING/CRITICAL states
- **Services** — manual override and forced recalculation

## Installation

### HACS (recommended)

1. Open **HACS → Integrations → ⋮ → Custom repositories**
2. Add `https://github.com/mberglundmx/ha-energy-dispatcher`
3. Category: **Integration**
4. Search for **Energy Dispatcher**, install, and restart Home Assistant

### Manual

Copy `custom_components/energy_dispatcher/` to your Home Assistant `config/custom_components/` directory and restart.

## Configuration

### Global setup (config flow)

| Setting | Required | Description |
|---|---|---|
| Spot price sensor | Yes | Any sensor with current and upcoming hourly prices |
| Grid input sensor | Yes | Grid import power (W) |
| Grid output sensor | Yes | Grid export power (W) |
| Export compensation | Yes | Fixed amount added to spot price to estimate export revenue |
| Power guard strategy | No | Disabled (default) or simple hourly kWh limit |
| Price thresholds | No | Free / cheap / expensive classification |

### Per load (Configure → Add load)

| Setting | Description |
|---|---|
| Name | Display name; becomes the entity id |
| Required power (W) | Load power requirement; used for export and SOLAR checks |
| Prefer self-consumption | Allow `SOLAR` when grid output covers the load |
| Maximum export price | Self-consume only when export price is below this |
| Minimum minutes per day | Schedule cheapest allowed hours to meet daily runtime |
| Minimum minutes per week | Same for ISO week |
| Allowed grid sources | Free / cheap / normal / expensive |

## Entity output

Each load exposes `energy_dispatcher.<load_id>` with:

| State | Meaning |
|---|---|
| `ON` | Recommended to run now |
| `OFF` | Not recommended now |

Key attributes:

| Attribute | Description |
|---|---|
| `energy_mode` | `SOLAR`, `GRID_CHEAP`, `GRID_NORMAL`, `GRID_EXPENSIVE`, `GRID_FREE`, `BLOCKED` |
| `reason` | Machine-readable reason code |
| `reason_text` | Human-readable explanation |
| `next_opportunity` | Next recommended window (ISO datetime) when OFF |
| `grid_state` | `NORMAL`, `WARNING`, or `CRITICAL` (power guard) |
| `runtime_remaining_minutes` | Minutes still needed today/week |

## Services

| Service | Description |
|---|---|
| `energy_dispatcher.override` | Force ON or OFF for a duration |
| `energy_dispatcher.clear_override` | Clear active override |
| `energy_dispatcher.recalculate` | Force immediate recalculation |

## Architecture

Energy logic lives entirely in the integration. Automations only react to its output.

```
Price sensor ──┐
Grid input  ───┼──► Decision engine ──► energy_dispatcher.* ──► Your automations ──► Devices
Grid output ───┘
```

See [DEVSPEC.md](DEVSPEC.md) for the full design specification.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install pytest
.venv/bin/python -m pytest tests/ -v
```

## Debug logging

Add to `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.energy_dispatcher: debug
    homeassistant.loader: debug
```

Then restart Home Assistant. View logs under **Settings → System → Logs** (or **Developer tools → Logs**).

Alternatively, use **Settings → Devices & services → Energy Dispatcher → Enable debug logging** if your HA version supports per-integration debug toggles.

## License

MIT — see [LICENSE](LICENSE).
