# `switch.py` — Switch & Fan Toggle Platform

## Role

Defines the `switch` entity platform for Iotics devices. Creates `SwitchEntity` instances for:
- Power/light buttons (b1-b4, etc.) — on/off toggles
- Fan toggle buttons (l1, f1) — on/off toggle that pairs with the number entity for speed control

## Why Two Entity Types for Fans?

Fans have two separate controls in the Iotics system:
1. **On/Off toggle** — turns the fan on or off (a switch entity)
2. **Speed control** — sets fan speed 0-4 (a number entity)

The switch entity handles the on/off for fans. The number entity handles the speed. They share the same device and MQTT topic prefix but have different `unique_id` suffixes to avoid collision:

| Entity | unique_id | Example |
|--------|-----------|---------|
| Fan toggle (switch) | `iotics_{room}_fan` | `switch.iotics_kitchen_fan` |
| Fan speed (number) | `iotics_{room}_{label}` | `number.iotics_kitchen_fan_speed` |

## Entity Naming Convention

| Button type | Entity ID | Example |
|-------------|-----------|---------|
| Power/light (b1-b4) | `switch.iotics_{room_slug}_{label_slug}` | `switch.iotics_kitchen_light` |
| Fan toggle (l1, f1) | `switch.iotics_{room_slug}_fan` | `switch.iotics_kitchen_fan` |

The `_fan` suffix for fan toggles ensures unique_id uniqueness with the number platform.

## How Toggle Commands Work

When a user toggles a switch in the HA dashboard:

1. **`async_turn_on()` or `async_turn_off()`** is called
2. An HTTP command is sent directly to the device IP:

```
GET http://{device_ip}/action?button={btn}&status={0|1}
```

3. The in-memory `entity_state` dict is updated immediately
4. `async_write_ha_state()` is called to push the update to HA
5. The physical device responds → publishes MQTT message → MQTT handler updates state again (confirming)

### Why HTTP instead of MQTT for commands?

Iotics devices accept commands via simple HTTP GET requests on their local IP. This is faster and more reliable than publishing to MQTT (which would need to route through AWS IoT and back).

## State Reading

State is read from the coordinator's `entity_state` dict, which is updated by:
1. **Initial state push** (startup, via supervisor socket)
2. **MQTT messages** (real-time device state changes)
3. **Self-update** (immediately after sending a command)

```python
@property
def is_on(self) -> bool | None:
    state = self._coordinator.entity_state.get(self._entity_id_str, "off")
    return state == STATE_ON
```

## Device Registry Integration

Each switch entity is linked to its parent Iotics device via `DeviceInfo`:

```python
self._attr_device_info = DeviceInfo(
    identifiers={(DOMAIN, token)},
    name=device_name,
    manufacturer="Iotics",
    model="Iotics Smart Switch",
)
```

This makes the entity appear under Settings > Devices & Services, grouped under its device.
