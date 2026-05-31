# Architecture Guide — Iotics Switches Addon for Home Assistant

This document explains how the addon works, from start to finish, in plain language. By the end, you should understand exactly what happens when you toggle a switch in your HA dashboard or press a physical Iotics button.

---

## Table of Contents

1. [What Is This Addon?](#1-what-is-this-addon)
2. [The Big Picture](#2-the-big-picture)
3. [Startup Sequence (What Happens When You Click Start)](#3-startup-sequence)
4. [The Four Parallel Systems](#4-the-four-parallel-systems)
5. [Data Flow: Dashboard Toggle → Physical Device](#5-data-flow-dashboard-toggle--physical-device)
6. [Data Flow: Physical Button Press → HA Update](#6-data-flow-physical-button-press--ha-update)
7. [How Entities Are Created](#7-how-entities-are-created)
8. [Error Recovery (What Happens When Things Go Wrong)](#8-error-recovery)
9. [Security Model](#9-security-model)
10. [File-by-File Breakdown](#10-file-by-file-breakdown)

---

## 1. What Is This Addon?

This addon connects your **Iotics smart home WiFi switches** (available at [https://www.iotics.io](https://www.iotics.io)) to **Home Assistant** so you can control everything from one place.

The challenge it solves: Iotics devices have their own app and use a proprietary system (MQTT via AWS IoT + their own cloud API). This addon speaks both languages — it talks to Iotics systems AND talks to Home Assistant — acting as a **translator** between the two.

---

## 2. The Big Picture

Here's a bird's-eye view of all the systems involved:

```
                    ┌─────────────────────────────────────┐
                    │         Your Home Network            │
                    │                                      │
                    │  ┌──────────────────────────────┐    │
                    │  │   Home Assistant (HA OS)      │    │
                    │  │                              │    │
                    │  │  ┌──────────────────────┐   │    │
                    │  │  │  Iotics Switches Addon │   │    │
                    │  │  │  (Docker Container)   │   │    │
                    │  │  │                       │   │    │
                    │  │  │  bridge.py ─── runs   │   │    │
                    │  │  │  all the logic        │   │    │
                    │  │  └──────────┬───────────┘   │    │
                    │  │             │               │    │
                    │  │  ┌──────────▼───────────┐   │    │
                    │  │  │  HA Core             │   │    │
                    │  │  │  (manages entities,  │   │    │
                    │  │  │   dashboard, APIs)   │   │    │
                    │  │  └──────────┬───────────┘   │    │
                    │  └─────────────┼───────────────┘    │
                    │                │                     │
                    │     ┌──────────▼──────────┐         │
                    │     │  Your Iotics Devices  │         │
                    │     │  (switches, fans,    │         │
                    │     │   lights in your     │         │
                    │     │   home)              │         │
                    │     └──────────────────────┘         │
                    └─────────────────────────────────────┘

                              │            ▲
                    ┌─────────▼────────────┴──────────┐
                    │         Internet                  │
                    │                                   │
                    │  ┌──────────────┐  ┌──────────┐  │
                    │  │ Iotics Cloud │  │ AWS IoT  │  │
                    │  │ API          │  │ MQTT     │  │
                    │  │ (REST)       │  │ (WSS)    │  │
                    │  └──────────────┘  └──────────┘  │
                    └───────────────────────────────────┘
```

There are **4 communication channels** shown here:

| Channel | What it does | Direction |
|---------|-------------|-----------|
| **A. Addon ↔ Iotics Cloud API** | Discover devices, get initial state | Both ways |
| **B. Addon ↔ AWS IoT MQTT** | Real-time device state updates | Device → HA |
| **C. Addon ↔ HA Core** | Create entities, detect dashboard toggles | Both ways |
| **D. Addon ↔ Iotics Devices** | Send commands (HTTP to device IP) | HA → Device |

### A Note About Device Communication

When you toggle a switch in your HA dashboard, the addon sends an **HTTP command directly to the Iotics device on your local network** (using the device's IP address like `192.168.1.100`). It does NOT go through the internet. This makes it fast and reliable.

However, the addon ALSO connects to the internet for two things:
1. **Iotics Cloud API** — to discover your devices and get their current states
2. **AWS IoT** — to receive real-time updates when you press a physical button

---

## 3. Startup Sequence

When you click "Start" in the addon, here is exactly what happens, step by step:

### Phase 1: Read Configuration

```
HA Addon Config (UI)
        │
        ▼
/data/options.json  ─── contains: email, password, appid
        │
        ▼
bridge.py reads this file → stores in memory
```

The supervisor automatically writes the config fields you filled in (email, password, appid) into a file at `/data/options.json` inside the container. The bridge reads this file at startup.

### Phase 2: Discover Devices

```
bridge.py
        │
        ▼
POST https://api.iotics.io/user/login
  Body: { email, password, appid }
        │
        ▼
Response: session token (like a temporary login key)
        │
        ▼
POST https://api.iotics.io/device/
  Body: { session, appid }
        │
        ▼
Response: list of ALL your devices
  Each device has: name, MAC address, IP,
  list of switches with labels and states
```

This is how the addon knows what devices you have. It does NOT need any hardcoded configuration — it discovers everything from the cloud.

### Phase 3: Create HA Entities

```
For each device:
  For each switch/button on that device:
    Create an HA entity:
      - If it's a light/fan switch → input_boolean.iotics_{room}_{label}
      - If it's a fan speed slider → input_number.iotics_{room}_{label}
    Set its state to match the current device state
```

These entities now show up in Home Assistant. You can add them to any dashboard.

### Phase 4: Start the Four Listeners

Now the addon starts **four parallel systems** that all run simultaneously:

```
┌──────────────────────────────────────────────┐
│               main()                           │
│                                                │
│   Thread 1: ha_call_service_listener()  ◄────┤ Dashboard toggle detector
│   Thread 2: ha_poll_listener()          ◄────┤ Fallback state checker
│   Thread 3: snapshot_loop()             ◄────┤ Device re-discovery
│   Thread 4: run_mqtt()                  ◄────┤ Real-time MQTT listener
│                                               │
└──────────────────────────────────────────────┘
```

Each of these runs forever in its own loop, explained in detail below.

---

## 4. The Four Parallel Systems

### System 1: HA Call Service Listener (Dashboard Toggle Detector)

**Purpose:** Detect when you toggle a switch in the HA dashboard.

```
┌──────────────────────────────────────────┐
│  ha_call_service_listener()               │
│                                           │
│  Connect to HA via WebSocket              │
│  Subscribe to "call_service" events       │
│                                           │
│  ┌──────────────┐                         │
│  │ Wait for      │                         │
│  │ event...     │                         │
│  └──────┬───────┘                         │
│         │                                  │
│         ▼                                  │
│  Received: User toggled                    │
│  "input_boolean.iotics_kitchen_light"      │
│         │                                  │
│         ▼                                  │
│  Look up in STATE list:                    │
│    What device? What button?               │
│    What IP? What hardware token?           │
│         │                                  │
│         ▼                                  │
│  Send command to device:                   │
│  HTTP GET http://192.168.1.100/action      │
│  ?button=b2&status=1                       │
│         │                                  │
│         ▼                                  │
│  Also write state to HA:                   │
│  POST /api/states/input_boolean.iotics_..  │
│  → state: "on"                             │
└──────────────────────────────────────────┘
```

**Why call_service?** Normally, addons listen for `state_changed` events to detect dashboard toggles. But a bug in HA 2026.5.x causes `state_changed` events to stop arriving after a few seconds. However, `call_service` events (which fire BEFORE the state changes) work reliably. So we intercept the service call before it reaches HA's broken handler.

**What is "call_service"?** When you click a toggle in the dashboard, HA internally says "I need to call the service `input_boolean.toggle` on entity X." That service call is a `call_service` event — and we catch it before HA processes it.

### System 2: HA Poll Listener (Fallback)

**Purpose:** Watch for state changes that the call_service listener might miss.

```
┌──────────────────────────────────────────┐
│  ha_poll_listener()                      │
│                                           │
│  Every 2 seconds:                         │
│  GET /api/states (ALL entities)           │
│         │                                  │
│         ▼                                  │
│  Is any iotics entity's state different    │
│  from what we last saw?                    │
│         │                                  │
│   ┌─────┴─────┐                           │
│   │ YES        │ NO                        │
│   ▼            ▼                           │
│  Was the      Do nothing                  │
│  change from  (wait 2s,                   │
│  iotics_mqtt?  check again)               │
│   │                                         │
│   ├── YES → It was us, skip               │
│   └── NO  → External change!              │
│             Forward to device             │
└──────────────────────────────────────────┘
```

This exists because there are other ways an entity's state can change besides clicking a toggle:
- Another automation changing the state
- Someone writing directly to the States API
- The call_service listener missed an event due to a bug

The poll adds an extra layer of reliability.

### System 3: Snapshot Loop (Device Re-discovery)

**Purpose:** Periodically check the Iotics cloud for new/removed devices.

```
┌──────────────────────────────────────────┐
│  snapshot_loop()                         │
│                                           │
│  Every 5 minutes:                         │
│  Call Iotics Cloud API                    │
│  Get full device list                     │
│         │                                  │
│         ▼                                  │
│  Compare with what we know                │
│         │                                  │
│   ┌─────┴─────┐                           │
│   │ Changed    │ Same                      │
│   ▼            ▼                           │
│  Rebuild       Do nothing                 │
│  STATE list    (wait 5 min)               │
│  Sync to HA                                │
│  (creates new entities,                   │
│   updates states)                         │
└──────────────────────────────────────────┘
```

This handles:
- **New device added** → appears in HA within 5 minutes
- **Device removed** → its entities stop updating (they become "unavailable" naturally)
- **Label renamed** → entities update with new names

### System 4: MQTT WSS Listener (Real-Time Device State)

**Purpose:** Receive instant updates when a physical button is pressed on an Iotics device.

```
┌──────────────────────────────────────────┐
│  run_mqtt()                              │
│                                           │
│  Connect to AWS IoT via WSS on port 443  │
│  Using SigV4 signing (a secure auth      │
│  method from Amazon Web Services)        │
│         │                                  │
│         ▼                                  │
│  Subscribe to: io/{token}/#               │
│  (one subscription per device)            │
│         │                                  │
│  ┌──────────────┐                         │
│  │ Wait for      │                         │
│  │ MQTT message  │                         │
│  └──────┬───────┘                         │
│         │                                  │
│         ▼                                  │
│  Received: io/abc123/b2/hw = "1"          │
│  Meaning: device abc123, button b2,       │
│  is now ON                                 │
│         │                                  │
│         ▼                                  │
│  Update STATE list                         │
│  POST to HA: entity state = "on"          │
│         │                                  │
│  ┌──────────────┐                         │
│  │ Every 15s:    │                         │
│  │ Check if      │                         │
│  │ connected     │                         │
│  └──────┬───────┘                         │
│         │                                  │
│   ┌─────┴─────┐                           │
│   │ Not        │ Connected                 │
│   │ connected  │ + recent msg              │
│   ▼            ▼                           │
│  Reconnect     Keep waiting               │
│  (wait 5s)                                │
└──────────────────────────────────────────┘
```

**Why WSS and not regular MQTT?** Iotics devices use AWS IoT, which requires WebSocket Secure (WSS) on port 443. The addon uses SigV4 (Signature Version 4) to sign the WebSocket URL — this is Amazon's authentication method that proves the addon has the right credentials to connect.

**The watchdog:** Every 15 seconds, the addon checks if MQTT is still connected. If no message arrives for 120 seconds, it assumes the connection is dead and reconnects. This handles network blips and server restarts.

---

## 5. Data Flow: Dashboard Toggle → Physical Device

Here's the complete journey when you click a toggle in your HA dashboard:

```
YOU CLICK TOGGLE IN HA DASHBOARD
              │
              ▼
[1] HA Core fires: "call_service"
    Event details:
    - Domain: "input_boolean"
    - Service: "toggle"
    - Entity: "input_boolean.iotics_kitchen_light"
              │
              ▼
[2] Addon's WebSocket receives this event
    ha_call_service_listener() wakes up
              │
              ▼
[3] _handle_call_service() determines the target state:
    - If service = "toggle" → read current HA state, flip it
    - If service = "turn_on" → target = "on"
    - If service = "turn_off" → target = "off"
    - If service = "set_value" → target = the number value
              │
              ▼
[4] Addon looks up the entity in STATE list:
    Entity: "input_boolean.iotics_kitchen_light"
    → Find match in STATE records
    → Get: hardwaretoken, button, IP address
              │
              ▼
[5] Send command to physical device:
    IF it's a fan speed (btn starts with "l"):
        Publish MQTT message: io/{token}/l1/sw = "1"
    ELSE (regular switch):
        HTTP GET: http://192.168.1.100/action?button=b2&status=1
              │
              ▼
[6] Device receives command:
    - Light turns ON (physically)
    - Device publishes MQTT: io/{token}/b2/hw = "1" (state update)
              │
              ▼
[7] Addon receives the MQTT state update:
    update_from_mqtt() processes it
    → Updates STATE list
    → POSTs to HA: entity state = "on"
              │
              ▼
[8] HA dashboard shows the switch as ON
```

**Total time:** 100-500 milliseconds. The light turns on almost instantly.

---

## 6. Data Flow: Physical Button Press → HA Update

Now the reverse — you press a physical Iotics switch on the wall:

```
YOU PRESS PHYSICAL IOTICS SWITCH
              │
              ▼
[1] Iotics device changes state:
    - Light turns ON
    - Device publishes MQTT: io/{token}/b2/hw = "1"
              │
              ▼
[2] MQTT message arrives at AWS IoT
              │
              ▼
[3] Addon's persistent MQTT connection receives it
    on_message() callback fires
              │
              ▼
[4] update_from_mqtt() processes the message:
    - Parses topic → extracts device token + button
    - Looks up in BY_TOPIC dict
    - Updates STATE list entry
    - If button is "l*" (fan speed): state = the number (0-4)
    - If button is "b*" or "f*" (switch): state = ON/OFF
              │
              ▼
[5] ha_post_state() writes to HA:
    POST /api/states/input_boolean.iotics_kitchen_light
    Body: {"state": "on", "attributes": {"source": "iotics_mqtt"}}
              │
              ▼
[6] HA dashboard updates to show the light is ON
```

**Total time:** 500ms - 2 seconds. Almost instant.

---

## 7. How Entities Are Created

Every time the addon discovers devices from the Iotics cloud, it creates HA entities. Here's the naming scheme:

```
Device name from Iotics: "Kitchen"
Button: b2 with label "Light"

→ Entity ID: input_boolean.iotics_kitchen_light

Device name: "Bedroom P1"
Button: l1 with label "Fan Speed"

→ Entity ID: input_number.iotics_bedroom_p1_fan_speed
```

The name is built like this:

```
{domain}.iotics_{room_slug}_{button_label_slug}
```

Where:
- **domain**: `input_boolean` for switches, `input_number` for fan speeds
- **iotic**: prefix to identify this is from the addon
- **room_slug**: the device name, lowercased, spaces replaced with underscores
- **button_label_slug**: the button's label, same treatment

The `slug()` function converts any label into a safe format:
- "Hall Middle Light" → "hall_middle_light"
- "Fan Speed 1" → "fan_speed_1"
- "AC" → "ac"

### Why input_boolean and input_number?

| HA Entity Type | What it can do | When we use it |
|---------------|---------------|----------------|
| `input_boolean` | On/Off toggle | Regular switches, lights |
| `input_number` | Numeric value (0-4) | Fan speed sliders |

These are the simplest entity types in HA. They don't try to control anything — they just store a value. The addon does the actual device control separately.

---

## 8. Error Recovery

### MQTT Disconnection

If the MQTT connection drops:
1. The watchdog detects no message in 120 seconds
2. It disconnects and waits 5 seconds
3. It reconnects with a fresh connection
4. It re-subscribes to all device topics
5. In the meantime, the cloud REST API (polled every 5 minutes) keeps states reasonably current

### HA WebSocket Disconnection

If the HA call_service WebSocket drops:
1. The recv() call raises an exception
2. The listener exits the inner loop, waits 5 seconds
3. It reconnects and re-subscribes
4. During the gap, the HA poll listener (every 2 seconds) acts as fallback

### HA Core Restart

If HA restarts:
1. The addon container also restarts (they're linked)
2. All four systems start fresh
3. Devices are re-discovered from cloud
4. States are re-synced to HA
5. MQTT reconnects
6. Everything is back to normal within 30 seconds

### No Internet

If the internet goes down:
- **Cloud API** — device discovery and state sync pause until internet returns
- **MQTT** — stays disconnected, retries every 5 seconds
- **Dashboard toggles** — STILL WORK because commands go directly to devices on your local network via HTTP
- **Physical button presses** — still change devices, but HA doesn't see the update until MQTT reconnects

This means your switches keep working locally even if your internet is down.

---

## 9. Security Model

### What the Addon Needs Access To

| Resource | Why | How |
|----------|-----|-----|
| Iotics email + password | Login to cloud API | Stored in `/data/options.json`, never exposed |
| HA Supervisor API | Create entities, get states | Uses `SUPERVISOR_TOKEN` env var (auto-provided by HA) |
| AWS IoT (internet) | Real-time MQTT | Uses built-in Iotics credentials |
| Your local network | Send commands to device IPs | Direct HTTP on your LAN |

### What the Addon Does NOT Do

- ❌ Does NOT store your credentials in any file outside the container
- ❌ Does NOT send your data to any third parties (only Iotics cloud + AWS IoT)
- ❌ Does NOT expose ports or accept incoming connections
- ❌ Does NOT require you to generate any tokens or certificates

### Token Handling

- **HA Supervisor Token**: Automatically injected by HA into the container environment. The addon never stores it. If the container is restarted, a new token is provided.
- **Iotics Cloud Session**: Created fresh on each login (every 5 minutes). Not stored. Expires naturally.
- **AWS Credentials**: Built into the addon code (same for all users). These are extracted from the public Iotics mobile app.

---

## 10. File-by-File Breakdown

### config.yaml

The addon's ID card. Tells HA:
- What the addon is called
- What version it is
- What hardware it runs on (aarch64 for Raspberry Pi 4/5, amd64 for x86)
- What settings the user needs to fill in (email, password, appid)
- That it needs network access (`host_network: true`)
- That it needs to talk to the HA API (`homeassistant_api: true`)

### Dockerfile

The recipe for building the addon container. Tells Docker:
1. Start from the HA base image (`FROM $BUILD_FROM`)
2. Install Python 3
3. Install the two Python libraries: `paho-mqtt` (for MQTT) and `websockets` (for HA WebSocket)
4. Copy `run.sh` and `bridge.py` into the container
5. Set `run.sh` as the command to run on startup

### run.sh

The entrypoint script. It:
1. Reads the user's settings from `/data/options.json` using `bashio` (HA's helper tool)
2. Checks that email and password were provided
3. Logs the configuration
4. Launches `bridge.py`

### bridge.py

The main logic. Contains:

- **Configuration loading** — reads email/password/appid
- **AWS credential extraction** — gets the built-in AWS keys
- **HA API helpers** — `ha_post_state()` and `ha_get()` for talking to HA
- **SigV4 signing** — `aws_iot_wss_path()` generates secure MQTT URLs
- **Cloud API** — `get_devices_from_cloud()` discovers devices
- **State management** — `rebuild_from_devices()`, `sync_all_states_to_ha()`, `update_from_mqtt()`
- **Device command** — `send_command_to_device()` sends HTTP/MQTT to physical devices
- **Four listener threads** — call_service, poll, snapshot, MQTT
- **Main** — wires everything together and starts it

### logo.svg

The icon that appears in the HA addon store. Shows a house with a signal wave, representing a smart home.

---

## Technical Details (For Developers)

### Why paho-mqtt with VERSION2 callbacks?

The addon uses `paho-mqtt` version 2.1.0 or later, which requires `CallbackAPIVersion.VERSION2` for the callback functions. In VERSION2:
- `on_connect` receives 5 arguments (client, userdata, flags, reason_code, properties) instead of 4
- `on_disconnect` receives 5 arguments instead of 3
- Reason codes provide more detailed error information

### Why no client certificates for MQTT?

AWS IoT supports two authentication methods:
1. **X.509 client certificates** (port 8883) — requires certificate files
2. **SigV4 WebSocket** (port 443) — uses AWS IAM keys, no certs needed

The addon uses method 2 because it's simpler — no certificate files to manage. The IAM keys are built into the addon.

### Why http://supervisor/core instead of http://localhost:8123?

In an HA addon, the container has access to a special proxy at `http://supervisor/core` that routes to the main HA instance. This is the recommended way for addons to talk to HA. Port 8123 is not available inside addon containers because HA's internal webserver doesn't bind to that port directly.

The `SUPERVISOR_TOKEN` environment variable is automatically provided by the HA supervisor to authenticate requests through this proxy.
