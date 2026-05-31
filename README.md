# Iotic Switches Addon for Home Assistant

[![GitHub release (latest by date)](https://img.shields.io/github/v/release/keithcardozo10-dev/Iotic-Switches-Addon-For-Home-Assistant)](https://github.com/keithcardozo10-dev/Iotic-Switches-Addon-For-Home-Assistant/releases)
[![GitHub all releases](https://img.shields.io/github/downloads/keithcardozo10-dev/Iotic-Switches-Addon-For-Home-Assistant/total)](https://github.com/keithcardozo10-dev/Iotic-Switches-Addon-For-Home-Assistant/releases)

A Home Assistant addon that integrates [Iotics](https://iotics.io) smart home devices. Fully automatic device discovery — just enter your Iotics email and password, and all switches, lights, fans, and ACs are automatically detected and controllable from your HA dashboard.

## Features

- **Auto-discovery** — All your Iotics devices are discovered from the cloud API. No manual configuration.
- **Real-time state sync** — Connects to AWS IoT via MQTT WSS for instant device state updates.
- **Dashboard toggle support** — Toggle switches and set fan speeds directly from the HA Lovelace dashboard.
- **Fan speed control** — Supports fan speed adjustment via MQTT (l1 buttons).
- **Runs inside HA** — No external dependencies. Runs as a native HA addon container.
- **Survives restarts** — Auto-starts with HA.

---

## Installation Guide (Step by Step)

### Step 1: Add the Repository to Home Assistant

1. Open your Home Assistant web interface.
2. Go to **Settings** (sidebar) → **Add-ons** → **Add-on Store** (bottom right).
3. Click the **three dots** (⋮) menu in the top-right corner → **Repositories**.
4. In the "Add repository" field, paste this URL:
   ```
   https://github.com/keithcardozo10-dev/Iotic-Switches-Addon-For-Home-Assistant
   ```
5. Click **Add**.
6. The page will reload. You should see "Iotic Switches Addon" appear under the "Local add-ons" section.

### Step 2: Install the Addon

1. Click on **Iotic Switches Addon** in the addon list.
2. Click **Install**.
   - This builds the Docker container with all dependencies (paho-mqtt, websockets).
   - It takes 2-5 minutes depending on your HA hardware. Watch the log output for progress.
3. Wait for "Installation completed" to appear in the log.

### Step 3: Configure Your Iotics Credentials

1. Go to the **Configuration** tab of the addon.
2. Fill in the following fields:

   | Field | Required | Default | What to enter |
   |-------|----------|---------|---------------|
   | `iotics_email` | Yes | — | The email address you use to log into the Iotics mobile app |
   | `iotics_password` | Yes | — | The password for your Iotics account |
   | `iotics_appid` | No | `696f74696373617070` | This is pre-filled. Only change it if the Iotics API rejects your login. |

3. Leave `iotics_appid` as-is unless the addon fails to connect (see troubleshooting below).

### Step 4: Start the Addon

1. Go to the **Info** tab.
2. Click **Start**.
3. Wait about 10-15 seconds.
4. Go to the **Log** tab. You should see something like this:

   ```
   [INFO] Iotics Smart Home Bridge starting...
   [INFO] Loaded options: email=your@email.com, appid=696f74696373617070
   [INFO] REST API: 12 devices discovered
   [INFO] Snapshot: 61 items, 12 IPs from REST API
   [INFO] Synced 61/61 states to HA
   [INFO] HA listeners started
   [INFO] HA call_service listener started
   [INFO] HA poll: cached 71 entity states
   [INFO] Connecting MQTT WSS...
   [INFO] MQTT connected: Success
   [INFO] Subscribed to 12 devices
   ```

### Step 5: Verify It's Working

1. Go to your HA dashboard.
2. Click the **Iotic Switches** dashboard that was created in your sidebar.
3. You should see all your Iotics devices listed with their current states.
4. Try toggling a switch — it should control your physical Iotics device in real time.
5. Press a physical Iotics switch — the state should update in HA within 1-2 seconds.

### Step 6: Set Addon to Start on Boot (Recommended)

1. In the **Info** tab of the addon.
2. Toggle **Start on boot** to ON.
3. Toggle **Watchdog** to ON (this restarts the addon if it crashes).

---

## Troubleshooting

### "No devices discovered" or login fails
- Double-check your Iotics email and password in the Configuration tab.
- Try logging into the Iotics mobile app with the same credentials to confirm they work.

### MQTT stays disconnected
- The addon will keep retrying automatically. Wait 30-60 seconds.
- If it never connects, check that your HA has internet access (AWS IoT is external).
- The bridge still works without MQTT — it polls the cloud API every 5 minutes for state updates.

### Dashboard shows "unavailable" entities
- Wait 2-5 seconds for the bridge to sync states on startup.
- If entities stay unavailable for more than 30 seconds, check the Log tab for errors.

### Port 8123 connection refused (this is normal!)
The addon uses `http://supervisor/core` internally to talk to HA. It does NOT use port 8123.

---

## Configuration Reference

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `iotics_email` | Yes | — | Your Iotics account email |
| `iotics_password` | Yes | — | Your Iotics account password |
| `iotics_appid` | No | `696f74696373617070` | Iotics API app ID (decodes to "ioticsapp" — standard for all users) |

### Finding Your App ID

The app ID is embedded in the Iotics mobile app and is the same for all users.

**Default:** `696f74696373617070` (decodes to ASCII `ioticsapp`)

If this doesn't work (e.g., your Iotics app version uses a different ID):

- **iOS:** Use iMazing to browse the Iotics app files → find `main.jsbundle` → search for a 16-character hex string pattern `appid:"..."`.
- **Android:** Extract the APK → search the bundle for the same pattern.

---

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

---

## Development

### Repository Structure

```
Iotic-Switches-Addon-For-Home-Assistant/
├── config.yaml     # Addon configuration & schema
├── Dockerfile      # Container build
├── run.sh          # Entrypoint
├── bridge.py       # The bridge (main logic)
├── logo.svg        # Addon icon
└── README.md       # This file
```

### Testing Locally

The addon can be deployed as a local addon on any HA OS system:

```bash
# Copy to your HA host
scp -r Iotic-Switches-Addon-For-Home-Assistant/ hassio@<your-ha-ip>:/addons/iotics-addon/

# Rebuild and start
sudo docker exec hassio_cli ha apps rebuild local_iotics_smart_home_bridge
sudo docker exec hassio_cli ha apps start local_iotics_smart_home_bridge
```

---

## License

MIT
