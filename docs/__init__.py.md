# `__init__.py` — Integration Entry Point & Setup Coordinator

## Role

This is the entry point Home Assistant loads when the Iotics custom integration starts. It's responsible for the entire lifecycle:

1. **Setup** (`async_setup_entry`): Called when a user adds the Iotics integration via Settings > Devices & Services
2. **Coordination**: Creates a `DataUpdateCoordinator` that polls the Iotics cloud API every 5 minutes (backup state sync)
3. **MQTT bridge setup**: Initialises the MQTT WebSocket client that provides real-time device state updates
4. **Device registration**: Registers each Iotics device in the HA device registry so they appear under Settings > Devices & Services
5. **Entity state management**: Builds an entity state map and an O(1) MQTT lookup table for efficient message handling
6. **Initial state push**: On startup, pushes all current device states to HA via the supervisor Unix socket (one-shot)
7. **Real-time message handler**: Routes incoming MQTT messages to update the correct entity state
8. **Service call interception**: Listens for `call_service` events to handle fan speed changes from the UI
9. **Teardown** (`async_unload_entry`): Cleanly disconnects MQTT and removes entities when the integration is removed

## Key Design Decisions

### Supervisor Unix Socket for Initial State Push

On first startup, the integration needs to tell HA the current state of all devices. It does this by writing directly to the supervisor's Unix socket at `/run/supervisor/core.sock` using the `SUPERVISOR_TOKEN` environment variable.

```python
def _push_state_to_supervisor(eid: str, state_val: str) -> bool:
```

This is a **one-shot operation at startup only**. After that, state updates are driven by MQTT messages via `coordinator.async_update_listeners()`.

### Why NOT push all states on every MQTT message

Originally the integration pushed states via the supervisor socket on every MQTT update. This caused a race condition: if a user toggled a switch in the HA UI, the MQTT message from the physical switch (which arrives after the hardware responds) would revert the state back by overwriting the user's action.

The fix: MQTT messages only update the in-memory `entity_state` dict and call `coordinator.async_update_listeners()`. Each entity then reads its state from the dict and calls `async_write_ha_state()` itself.

### Coordinator Init Order

The coordinator must be stored in `hass.data[DOMAIN][COORDINATOR]` **before** calling `async_forward_entry_setups()`. If entity platforms like `switch.py` try to access the coordinator during their `async_setup_entry` but it hasn't been stored yet, they'll get a KeyError.

### O(1) MQTT Lookup

Instead of iterating all devices/buttons on every MQTT message, the integration builds a flat dict at startup:

```python
mqtt_lookup["{token}_{btn}"] = {"eid": "...", "is_fan": bool, "ip": "...", "btn": "..."}
```

MQTT topic format: `io/{token}/{btn}/hw` — the `{token}_{btn}` key is extracted directly.

### Fan Entity Pairing

Fan buttons generate TWO entities:
- `number.iotics_{room}_{label}` — fan speed (0-4)
- `switch.iotics_{room}_fan` — on/off toggle for the fan

The switch uses `_fan` suffix to avoid unique_id collision with the number entity's `_fan_speed` suffix.

### Call Service Interception Scope

The `call_service` listener only handles `number.set_value` for fan speeds. Switch toggles are handled directly by `IoticsSwitch.async_turn_on/off()` in `switch.py`. This avoids double-fire race conditions where the call_service listener and the entity's own method both try to send commands.

## Control Flow

```
HA starts → async_setup_entry() called
  ├─ Create IoticsApiClient (cloud API)
  ├─ Create IoticsMqttClient (MQTT WSS)
  ├─ Coordinator first refresh → discovers devices
  ├─ Register devices in HA device registry
  ├─ Build entity_state + mqtt_lookup
  ├─ Store coordinator in hass.data
  ├─ Forward to switch + number platforms
  ├─ Push initial states via Unix socket
  ├─ Start MQTT connection (background task)
  └─ Register call_service listener

MQTT message arrives → on_mqtt_message()
  ├─ Extract token + btn from topic
  ├─ O(1) lookup → find entity_id
  ├─ Update entity_state dict
  └─ coordinator.async_update_listeners()

User toggles switch → IoticsSwitch.async_turn_on/off()
  ├─ Send HTTP command to device IP
  ├─ Update entity_state
  └─ async_write_ha_state()

User sets fan speed → call_service listener
  ├─ Validate entity_id (number.iotics_*)
  ├─ Update entity_state
  ├─ Find device IP + button from mqtt_lookup
  └─ Send HTTP command to device
```
