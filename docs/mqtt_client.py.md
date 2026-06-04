# `mqtt_client.py` — AWS IoT MQTT WebSocket Client

## Role

Manages a persistent MQTT WebSocket Secure (WSS) connection to AWS IoT Core for real-time device communication. This is the exact replica of the Mac realtime server's MQTT approach.

## Architecture

```
                 WSS 443
  HA Integration ─────────── AWS IoT Core ─────────── Iotics Devices
  (this client)    SigV4     (message broker)   MQTT    (WiFi)
```

## Connection Details

| Parameter | Value |
|-----------|-------|
| Transport | `websockets` (not TCP) |
| Port | 443 (standard HTTPS — bypasses firewalls) |
| TLS | `ssl._create_unverified_context()` with `CERT_NONE` |
| Auth | SigV4-signed path via `aws_iot_wss_path()` |
| WS Header | `Sec-WebSocket-Protocol: mqtt` |
| Protocol | MQTT 3.1.1 |
| Keepalive | 30 seconds |

## Watchdog System

The MQTT client has a built-in watchdog that ensures the connection stays alive:

1. Every 15 seconds, the watchdog checks:
   - **Connection state**: If `_connected` is False, reconnect immediately
   - **Silence timeout**: If no message received in 120 seconds, reconnect
2. On disconnect for any reason, auto-retries every 5 seconds
3. The watchdog runs as an asyncio task inside the `_connect_loop`

```python
MQTT_WATCHDOG_INTERVAL = 15   # Check every 15s
MQTT_WATCHDOG_TIMEOUT = 120   # Reconnect after 120s silence
MQTT_RECONNECT_DELAY = 5      # Wait 5s between retries
```

## Message Flow

```
Device publishes → AWS IoT → MQTT message received
  → on_message() callback fires
    → _message_callback(topic, payload) called
      → __init__.py's on_mqtt_message() processes it
        → Updates entity_state
          → coordinator.async_update_listeners()
```

### Topic Subscription

The client subscribes to one wildcard topic:

```
io/+/+/+/hw
```

This catches all device state updates (format: `io/{token}/{btn}/hw`), including the 5-part format for BLDC fans: `io/{token}/{btn}/is_bldc/hw`.

## Client Instance Management

The `_connect_loop` creates a completely fresh paho-mqtt `Client` instance on each connection attempt. This prevents stale state from a previous connection (hanging subscriptions, old callbacks) from affecting the new connection.

Each client gets a unique `client_id` combining `hass-iotics-` + timestamp + object id.

## Key Implementation Details

### Asyncio Bridge

paho-mqtt is a synchronous library. The client bridges to asyncio by:
1. Running blocking calls (`connect`, `publish`, `disconnect`) via `run_in_executor`
2. Using the synchronous `on_message` callback to schedule async work via `asyncio.run_coroutine_threadsafe()`

### TLS Verification Disabled

`ssl._create_unverified_context()` with `CERT_NONE` is used because the Iotics devices do not use standard AWS IoT certificates. This matches the standalone bridge pattern.

### Watchdog Loop Exit Conditions

The inner watchdog loop exits (triggering a reconnect) when:
- `_connected` becomes False (disconnect detected)
- No messages received for 120 seconds (silence timeout)
- `_running` becomes False (shutdown requested)

## Error Recovery

| Scenario | Recovery |
|----------|----------|
| Connection refused | Retry in 5s |
| DNS failure | Retry in 5s |
| TLS error | Retry in 5s |
| Random disconnect | Retry in 5s |
| 120s silence | Force reconnect |
| `_running=False` | Clean exit, no retry |
