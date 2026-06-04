# `number.py` — Fan Speed Control Platform

## Role

Defines the `number` entity platform for Iotics fan speed controls. Creates `NumberEntity` instances for fan buttons (l1, f1) that allow setting speed from 0 (off) to 4 (max).

## Entity Properties

| Property | Value |
|----------|-------|
| `native_min_value` | 0 |
| `native_max_value` | 4 |
| `native_step` | 1 |
| Entity ID format | `number.iotics_{room_slug}_{label_slug}` |

## MQTT Command Publishing

Unlike switch toggles (which use HTTP commands), fan speed changes are sent via **MQTT publish**:

```python
topic = f"io/{token}/{btn}/sw"
payload = status  # "0", "1", "2", "3", or "4"
```

The device receives the MQTT message via AWS IoT and sets its fan speed accordingly.

### Why MQTT for fan speeds?

Fan speed commands (0-4) use the `io/{token}/{btn}/sw` topic pattern. This is the standard Iotics protocol for fan speed control. HTTP commands on the `/action` endpoint only support binary on/off states.

## State Reading

State is read from the coordinator's `entity_state` dict as a float:

```python
@property
def native_value(self) -> float | None:
    raw = self.coordinator.entity_state.get(self.entity_id, "0")
    try:
        return float(raw)
    except (ValueError, TypeError):
        return 0.0
```

## How Fan Speed Changes Flow

```
User drags slider to 3 in HA
  → async_set_native_value(3.0)
    → status = "3"
    → MQTT publish: io/{token}/{btn}/sw = "3"
    → Update entity_state dict
    → async_write_ha_state()

Physical fan responds
  → MQTT message: io/{token}/{btn}/hw = "3"
    → MQTT handler updates entity_state
    → coordinator.async_update_listeners()
      → NumberEntity reads new state
      → async_write_ha_state() confirms
```
