# Iotic Switches Addon for Home Assistant

[![GitHub release (latest by date)](https://img.shields.io/github/v/release/keithcardozo10-dev/Iotic-Switches-Addon-For-Home-Assistant)](https://github.com/keithcardozo10-dev/Iotic-Switches-Addon-For-Home-Assistant/releases)
[![GitHub all releases](https://img.shields.io/github/downloads/keithcardozo10-dev/Iotic-Switches-Addon-For-Home-Assistant/total)](https://github.com/keithcardozo10-dev/Iotic-Switches-Addon-For-Home-Assistant/releases)

A Home Assistant addon that integrates [Iotics](https://iotics.io) smart home devices. Fully automatic device discovery — just enter your Iotics email and password.

## Features

- **Auto-discovery** — All your Iotics devices are discovered from the cloud API. No manual configuration.
- **Real-time state sync** — Connects to AWS IoT via MQTT WSS for instant device state updates.
- **Dashboard toggle support** — Toggle switches and set fan speeds directly from the HA Lovelace dashboard.
- **Fan speed control** — Supports fan speed adjustment via MQTT (l1 buttons).
- **Runs inside HA** — No external dependencies. Runs as a native HA addon container.
- **Survives restarts** — Auto-starts with HA.

## Installation

### Via Home Assistant Community Store (HACS)
*Coming soon — once the repo is submitted to the addon repository list.*

### Manual Installation

1. Copy the `ha-iotics-addon` folder to your HA `/addons/` directory:
   ```bash
   git clone https://github.com/keithcardozo10-dev/ha-iotics-addon /addons/ha-iotics-addon
   ```

2. In Home Assistant, go to **Settings → Add-ons → Local add-ons**.

3. Click **Check for updates** — the addon should appear as "Iotics Smart Home Bridge".

4. Click **Install** (this builds the Docker image, may take a few minutes).

5. Configure your Iotics credentials:
   - `iotics_email` — Your Iotics account email
   - `iotics_password` — Your Iotics account password
   - `iotics_appid` — The Iotics app ID (default: `696f74696373617070` — this is the standard Iotics API key, same for all users)

6. Click **Start**.

7. Check the **Log** tab to verify the bridge connects successfully.

## Configuration

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `iotics_email` | Yes | — | Your Iotics account email |
| `iotics_password` | Yes | — | Your Iotics account password |
| `iotics_appid` | No | `696f74696373617070` | Iotics API app ID (decodes to "ioticsapp") |

### Finding Your App ID

The app ID is embedded in the Iotics mobile app. It's the same for all users.

**Default:** `696f74696373617070` (decodes to ASCII `ioticsapp`)

If this doesn't work (e.g., your Iotics app version uses a different ID):

**iOS:** Use iMazing to browse the Iotics app files → find `main.jsbundle` → search for a 16-character hex string pattern `appid:"..."`.

**Android:** Extract the APK → search the bundle for the same pattern.

## How It Works

```
┌─────────────────────────────────────────┐
│            HA Addon Container            │
│                                          │
│  ┌─────────┐     ┌──────────────────┐   │
│  │ Iotics   │────▶│ AWS IoT MQTT WSS │   │
│  │ Cloud    │     │ (real-time state) │   │
│  │ API Poll │     └────────┬─────────┘   │
│  │ (5 min)  │              │             │
│  └────┬─────┘              │             │
│       │                    │             │
│  ┌────▼────────────────────▼──────────┐  │
│  │     HA REST API (state sync)       │  │
│  └────────────────┬───────────────────┘  │
│                   │                      │
│  ┌────────────────▼───────────────────┐  │
│  │  HA WebSocket (call_service events) │  │
│  └────────────────┬───────────────────┘  │
│                   │                      │
│  ┌────────────────▼───────────────────┐  │
│  │  HTTP/MQTT Commands to Devices     │  │
│  └────────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

1. **Device Discovery:** Bridge logs into Iotics cloud API, discovers all devices/buttons.
2. **State Sync:** Creates HA entities (`input_boolean` for switches, `input_number` for fan speeds) and syncs states.
3. **MQTT WSS:** Connects to AWS IoT for real-time device state updates.
4. **Dashboard Toggles:** Intercepts HA service calls (`call_service` events) and forwards commands to physical devices.
5. **Polling Fallback:** Polls HA state every 2s to catch direct API writes.

## Development

### Repository Structure

```
ha-iotics-addon/
├── config.yaml     # Addon configuration & schema
├── Dockerfile      # Container build
├── run.sh          # Entrypoint
├── bridge.py       # The bridge (main logic)
├── logo.png        # Addon icon
└── README.md       # This file
```

### Testing Locally

The addon can be deployed as a local addon on any HA OS system:

```bash
# Copy to your HA host
scp -r ha-iotics-addon/ hassio@<your-ha-ip>:/addons/iotics-addon/

# Rebuild and start
sudo docker exec hassio_cli ha apps rebuild local_iotics_smart_home_bridge
sudo docker exec hassio_cli ha apps start local_iotics_smart_home_bridge
```

## License

MIT
