# `iotics_api.py` — Iotics Cloud API Client & AWS IoT SigV4 Signing

## Role

This module handles everything to do with the Iotics cloud REST API and AWS IoT authentication:

1. **Iotics cloud login** — authenticates with email/password via `api.iotics.io/user/login`
2. **Device discovery** — fetches all devices registered to the user's account
3. **AWS IoT SigV4 signing** — generates signed WebSocket URLs for MQTT WSS connections
4. **Data extraction** — normalises device/button data into a flat list for entity creation
5. **3-attempt retry** — handles the Iotics cloud API's eventual-consistency bug where a fresh session token can be rejected on first use

## Iotics Cloud API

### Login Endpoint
```
POST https://api.iotics.io/user/login
{
  "emailid": "...",
  "password": "...",
  "action": "login",
  "appid": "696f74696373617070",
  "device_token": "iotics-ha-integration",
  "source": "mobile",
  "os": "ios"
}
```

Returns: `{"response": {"session": "<session_token>"}}`

### Device Discovery Endpoint
```
POST https://api.iotics.io/device/
{
  "session": "...",
  "appid": "696f74696373617070",
  "emailid": "...",
  "action": "getdevices"
}
```

Returns: `{"response": {"data": [device1, device2, ...]}}`

## Device Data Format

Each device from the API has this structure:

```python
{
  "hardwaretoken": "aabbccddeeff",    # Unique device ID (MAC without colons)
  "hardwarename": "Kitchen",           # Device name / room name
  "room": "Kitchen",                   # Same as hardwarename in current firmware
  "mac": "aa:bb:cc:dd:ee:ff",         # MAC address
  "ip": "192.168.1.100",               # Local IP (empty if offline)
  "switches": {
    "b1": {"status": 1, "label": "Light"},
    "b2": {"status": 0, "label": "Fan"},
    "b3": {"status": 1, "label": "Socket"},
    "l1": {"status": 0},              # Fan speed button (no label)
    "f1": {"status": 3}               # Alternate fan speed button (no label)
  }
}
```

### Field Notes

- **`hardwaretoken`** vs `mac`: The token is the MAC without colons AND lowercase. The `mac` field has colons and uppercase. Always prefer `hardwaretoken`.
- **`hardwarename`** vs `name`: The `name` field is ALWAYS null. Use `hardwarename`.
- **`status`** is an integer (0 or 1 for switches, 0-4 for fans), NOT a string.
- **Fan detection**: Fan buttons start with `l` or `f` (confirmed for both l1 and f1). They have no `type` field.

## SigV4 Signing for AWS IoT MQTT WSS

### Why SigV4

AWS IoT Core requires SigV4 authentication for MQTT WebSocket connections. The credentials are embedded in the Iotics mobile app bundle and are the same for ALL Iotics users — they are not personal secrets.

### How It Works

1. The AWS IAM access/secret keys are stored as split arrays to avoid GitHub secret scanners
2. A SigV4-signed URL path is generated with the `iotdevicegateway` service
3. The signed path is passed to paho-mqtt's `ws_set_options(path=...)`
4. The `Sec-WebSocket-Protocol: mqtt` header is required by AWS IoT

```python
def aws_iot_wss_path() -> str:
    # Returns: /mqtt?X-Amz-Algorithm=AWS4-HMAC-SHA256&...
```

### AWS IoT Endpoint

```
a3gmr1tawrdriq-ats.iot.us-east-1.amazonaws.com:443
```

## The `discover_direct()` Retry Pattern

The Iotics cloud has an eventual-consistency bug: a fresh session token is rejected on `getdevices` about 50% of the time. `discover_direct()` handles this with 3 attempts and 2-second delays:

```python
def discover_direct(self) -> list[dict]:
    for attempt in range(3):
        # Login fresh each attempt
        # Try getdevices with the session
        # If response is unexpected, clear session and retry
    return []
```

This is the method used by the coordinator on startup and every 5 minutes.

## Button Extraction

`extract_buttons(devices)` flattens all devices' switches into a uniform list:

```python
[
  {
    "token": "aabbccddeeff",
    "btn": "b1",
    "label": "Light",
    "status": "1",           # String!
    "is_fan": False,
    "ip": "192.168.1.100",
    "device_name": "Kitchen"
  },
  ...
]
```

Only buttons starting with `b`, `f`, or `l` are included (physical buttons only).
