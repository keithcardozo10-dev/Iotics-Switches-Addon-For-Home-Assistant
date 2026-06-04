# Iotics Switches Addon for Home Assistant

[![GitHub release (latest by date)](https://img.shields.io/github/v/release/keithcardozo10-dev/Iotics-Switches-Addon-For-Home-Assistant)](https://github.com/keithcardozo10-dev/Iotics-Switches-Addon-For-Home-Assistant/releases)

A **Home Assistant Custom Integration** (custom_component) that connects [Iotics](https://www.iotics.io) smart home WiFi switches directly into HA. Automatic device discovery, real-time state sync via MQTT, and full dashboard control — no cloud polling, no bridge containers, no YAML packages.

**What makes this different:** Your Iotics switches become first-class HA entities. They appear under Settings > Devices & Services as proper devices. You can use them in automations, trigger them from Zigbee/WiFi sensors, set fan speeds, and see state changes instantly — without relying on the Iotics cloud for every state read.

---

## Two Ways to Install

### Option A: Custom Integration (Recommended)

The `custom_components/iotics/` folder in this repo is a native HA Custom Integration. It runs as part of HA itself — no Docker, no add-on manager, no separate container.

**Install in 30 seconds:**

1. Copy the `custom_components/iotics/` folder into your HA `config/custom_components/` directory
2. Restart Home Assistant
3. Go to Settings > Devices & Services > Add Integration > Search "Iotics Smart Home"
4. Enter your Iotics email and password

That's it. Your devices appear automatically.

### Option B: HA Add-on (Legacy)

The `bridge.py` + `Dockerfile` + `config.yaml` in this repo also work as a traditional HA add-on (add the repo via the add-on store). This is the original approach and is still fully functional. See the add-on README section below for details.

---

## Why Custom Integration vs Add-on?

| Feature | Custom Integration (`custom_components/`) | HA Add-on (`bridge.py` + Docker) |
|---------|------------------------------------------|-----------------------------------|
| Installation | Copy folder, restart HA | Add repo to add-on store, install, configure |
| Runs as | Part of HA core | Separate Docker container |
| Entities appear under | Devices & Services (proper integration) | input_boolean / input_number (manual) |
| Real-time updates | MQTT WSS push | Cloud API poll (5s) |
| Resource usage | None (shares HA process) | ~100MB RAM container |
| Dashboard | Use your own Lovelace setup | Auto-generated dashboard |
| Dependencies | paho-mqtt (installed with integration) | paho-mqtt + websockets (in container) |

**Choose Custom Integration if:**
- You want devices to appear under Settings > Devices & Services with proper entities
- You want real-time state updates via MQTT (instant, no polling delay)
- You prefer no extra containers running
- You want to keep your existing Lovelace dashboards and just add cards

**Choose Add-on if:**
- You want an auto-generated dashboard with room grouping
- You prefer the add-on store UI for management
- You need entity creation via HA REST API (for complex state management)

---

## How It Works

```
                    ┌─────────────────────────────────────┐
                    │         Home Assistant (HA)          │
                    │                                      │
                    │  ┌──────────────────────────────┐    │
                    │  │  Iotics Custom Integration    │    │
                    │  │  (custom_components/iotics)   │    │
                    │  │                               │    │
                    │  │  __init__.py  ── Coordinator  │    │
                    │  │  iotics_api.py ── Cloud API   │    │
                    │  │  mqtt_client.py ── MQTT WSS   │    │
                    │  │  switch.py ──── Switch Entity │    │
                    │  │  number.py ──── Fan Speed     │    │
                    │  └──────────┬───────────────────┘    │
                    │             │                        │
                    └─────────────┼────────────────────────┘
                                  │
          ┌───────────────────────┼───────────────────────┐
          │                       │                       │
          ▼                       ▼                       ▼
  ┌──────────────┐     ┌──────────────────┐     ┌──────────────┐
  │  Iotics       │     │  AWS IoT MQTT    │     │  Iotics      │
  │  Cloud API    │     │  WSS (SigV4)     │     │  Devices     │
  │  (discovery)  │     │  (real-time)     │     │  (WiFi LAN)  │
  └──────────────┘     └──────────────────┘     └──────────────┘
```

### Data Flow

1. **Startup:** Integration logs into Iotics cloud API → discovers all devices and buttons → creates entities in HA → connects MQTT WSS for real-time updates
2. **Real-time updates:** When you press a physical Iotics switch → device publishes to AWS IoT MQTT → integration receives message → updates entity state instantly
3. **Dashboard toggles:** When you click a toggle in HA → integration sends HTTP command directly to the device's local IP → device responds → MQTT confirms the state change
4. **Fan speed control:** Drag slider → integration publishes MQTT command to AWS IoT → device receives and sets fan speed
5. **Backup sync:** Coordinator polls cloud API every 5 minutes to catch any missed state changes

### No Cloud Polling Loop

Unlike the old bridge approach, the custom integration does NOT poll HA's REST API for state changes. Instead:
- **Outbound** (HA → device): Direct HTTP commands on the LAN, or MQTT publish
- **Inbound** (device → HA): MQTT WSS push from AWS IoT

The only polling is a 5-minute cloud API check as a backup.

---

## How to Add the Custom Integration

### Step 1: Prerequisites

- Home Assistant (any installation: HAOS, Docker, Core, Supervised)
- An active Iotics account with devices registered
- An SSH or SMB connection to your HA config folder

### Step 2: Install the Custom Integration

```bash
# SSH into your HA host
ssh hassio@<ha-ip>

# Create custom_components directory if it doesn't exist
mkdir -p /config/custom_components/

# Copy the iotics folder from this repo
# (Option 1: via SCP from your computer)
scp -r custom_components/iotics/ hassio@<ha-ip>:/config/custom_components/iotics/

# (Option 2: via git clone on the HA host - if you have git installed)
cd /config/custom_components/
git clone https://github.com/keithcardozo10-dev/Iotics-Switches-Addon-For-Home-Assistant.git temp
cp -r temp/custom_components/iotics/ .
rm -rf temp
```

Or copy the `custom_components/iotics/` folder via SMB / HA Samba add-on to `/config/custom_components/iotics/`.

### Step 3: Restart HA

Go to Settings > System > Restart, or use the CLI:

```bash
ha core restart
```

### Step 4: Add the Integration

1. Go to **Settings > Devices & Services**
2. Click **+ Add Integration** (bottom right)
3. Search for **"Iotics Smart Home"**
4. Enter your:
   - **Email**: Your Iotics account email
   - **Password**: Your Iotics account password
   - **App ID**: Leave as default (`696f74696373617070`)
5. Click **Submit**

If successful, you'll see a confirmation. Your devices will appear within seconds.

### Step 5: Set Up Your Dashboard

The integration does NOT auto-generate a dashboard. Add entities manually to your Lovelace dashboard:

1. Go to your dashboard → Edit Dashboard → + Add Card
2. Choose **Entities** card
3. Search for `iotics` to see all available entities
4. Add the ones you want
5. You can group by room using `card` section dividers

Example Lovelace YAML for a room:

```yaml
type: entities
title: Kitchen
entities:
  - switch.iotics_kitchen_light
  - switch.iotics_kitchen_fan
  - number.iotics_kitchen_fan_speed
  - switch.iotics_kitchen_socket
```

---

## How to Add the HA Add-on (Legacy)

### Prerequisites

- Home Assistant OS or Supervised (with add-on support)
- Iotics devices on the same LAN

### Installation

1. Go to **Settings > Add-ons > Add-on Store**
2. Click the three dots (⋮) > **Repositories**
3. Add: `https://github.com/keithcardozo10-dev/Iotics-Switches-Addon-For-Home-Assistant`
4. Click **Add**
5. Find **Iotics Switches Addon** in the store and click **Install**
6. Go to **Configuration** tab, enter your email and password
7. Go to **Info** tab, click **Start**

---

## Features

| Feature | Supported | Notes |
|---------|-----------|-------|
| Auto device discovery | Yes | Via Iotics cloud API |
| Real-time state updates | Yes | Via MQTT WSS to AWS IoT |
| On/off toggle | Yes | HTTP command to device LAN IP |
| Fan speed control | Yes | 0-4 via MQTT publish |
| Multiple buttons per device | Yes | b1-b7, l1, f1 |
| Device registry | Yes | Appears under Settings > Devices & Services |
| No polling loop | Yes | MQTT push + 5min backup poll |
| Re-auth on session expiry | Yes | Via config flow reauth |
| Survives HA restart | Yes | Automatic |
| Manual entity restore | No | Integration creates entities dynamically |
| Dashboard auto-generation | No | Add-on only |

---

## Entity Reference

### Switch Entities (lights, sockets, fan toggles)

```
switch.iotics_{room_slug}_{label_slug}
switch.iotics_{room_slug}_fan      # For fan toggles
```

### Number Entities (fan speed)

```
number.iotics_{room_slug}_{label_slug}
```

Example for a Kitchen device with Light (b1) and Fan (l1):

| Entity | State | Type |
|--------|-------|------|
| `switch.iotics_kitchen_light` | on/off | Switch |
| `switch.iotics_kitchen_fan` | on/off | Switch |
| `number.iotics_kitchen_fan_speed` | 0-4 | Number |

---

## Architecture

### Integration (custom_components/iotics/)

```
custom_components/iotics/
├── __init__.py        # Entry point, coordinator, MQTT setup, call_service listener
├── iotics_api.py      # Iotics cloud API client, SigV4 signing, button extraction
├── mqtt_client.py     # MQTT WSS to AWS IoT with watchdog reconnect
├── config_flow.py     # Setup UI flow (add/reauth integration)
├── switch.py          # Switch entity platform (on/off toggles)
├── number.py          # Number entity platform (fan speed 0-4)
├── manifest.json      # Integration metadata
└── strings.json       # UI translation strings
```

### Add-on (Legacy)

```
├── config.yaml        # Add-on configuration schema
├── Dockerfile         # Container build instructions
├── run.sh             # Startup script
├── bridge.py          # Main bridge logic
├── logo.svg           # Add-on icon
└── docs/              # Add-on documentation
```

### Repository Root

```
├── custom_components/iotics/   # Custom integration (recommended)
├── docs/                       # Per-file documentation
├── README.md                   # This file
├── config.yaml                 # Add-on config (legacy)
├── Dockerfile                  # Container build (legacy)
├── run.sh                      # Startup script (legacy)
├── bridge.py                   # Original bridge (legacy)
└── logo.svg                    # Add-on icon
```

---

## Troubleshooting

### Custom Integration

| Problem | Likely Cause | Fix |
|---------|-------------|-----|
| "Iotics Smart Home" not in integration list | Folder not in right place | Check `custom_components/iotics/` exists in HA config dir, restart HA |
| Cannot connect during setup | Wrong email/password | Verify in Iotics mobile app |
| Entities don't appear | Cloud API issue | Check HA logs for "Iotics" messages |
| Switch toggles don't work | Device IP not reachable | Ensure Iotics devices are on the same LAN as HA |
| Fan speed control not working | MQTT not connected | Check logs for MQTT connection status |
| States reverting after toggle | Old bridge still running | Disable any old bridge scripts, restart HA |

### Add-on (Legacy)

| Problem | Likely Cause | Fix |
|---------|-------------|-----|
| Add-on doesn't appear in store | Wrong repo URL | Add `https://github.com/keithcardozo10-dev/Iotics-Switches-Addon-For-Home-Assistant` |
| No devices discovered | Wrong credentials | Double-check email/password in Configuration tab |
| MQTT stays disconnected | Internet access issue | Wait 30-60s for retry, check HA internet connectivity |
| "unavailable" entities | Startup sync delay | Wait 5-10 seconds, check Log tab |

### Debug Logs

Enable debug logging for the integration by adding to `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.iotics: debug
```

Check logs via **Settings > System > Logs** or:

```bash
docker logs homeassistant --tail 100 | grep -i iotics
```

---

## Development

### File Documentation

Each source file has detailed documentation in `docs/`:

- [__init__.py.md](docs/__init__.py.md) — Entry point, coordinator, state management
- [iotics_api.py.md](docs/iotics_api.py.md) — Cloud API client, SigV4 signing
- [mqtt_client.py.md](docs/mqtt_client.py.md) — MQTT WSS connection, watchdog
- [switch.py.md](docs/switch.py.md) — Switch entity platform
- [number.py.md](docs/number.py.md) — Fan speed number platform
- [config_flow.py.md](docs/config_flow.py.md) — Setup UI flow

### Requirements

- Python 3.12+
- `paho-mqtt>=2.1.0`
- Home Assistant 2025.1+ (tested on 2026.6.1)

### Local Development

The custom integration runs inside HA's Python environment. To test changes:

1. Edit files in `custom_components/iotics/`
2. Restart HA or reload the integration via Settings > Devices & Services
3. Check logs for errors

For the add-on version, rebuild the Docker container after changes.

---

## License

MIT
