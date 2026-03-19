# Relay Controller Notes

This folder contains hardware integration notes for the 8-slot relay controller.

## Backend Call Contract

Backend calls `RELAY_API_URL` with:

```json
{
  "slot_id": 1,
  "action": "open"
}
```

- `slot_id`: integer 1-8
- `action`: currently `open`

## Suggested Relay Mapping

Use this fixed mapping for controller firmware and cabinet wiring.

| Slot No. | Relay Channel | ESP32 GPIO |
|---|---:|---:|
| 1 | CH1 | GPIO23 |
| 2 | CH2 | GPIO22 |
| 3 | CH3 | GPIO21 |
| 4 | CH4 | GPIO19 |
| 5 | CH5 | GPIO18 |
| 6 | CH6 | GPIO5 |
| 7 | CH7 | GPIO17 |
| 8 | CH8 | GPIO16 |

Logic convention:
- Backend sends `slot_id` only.
- Relay controller resolves `slot_id -> relay channel -> GPIO` by this table.
- Recommended trigger mode: active-low (`LOW` = open, `HIGH` = idle), which matches most relay boards.

## Electrical Notes

- Relay board must support 3.3V trigger logic (direct from ESP32 GPIO).
- If board requires 5V trigger, use transistor/optocoupler level shifting.
- Use external power for relay coils and common ground with controller.
- Implement timeout so a door does not stay open forever on communication failure.

## Relay Controller JSON Example

The relay controller should accept:

```json
{
  "slot_id": 4,
  "action": "open"
}
```

Expected behavior:
- Convert slot 4 -> CH4 -> GPIO19.
- Set GPIO19 to trigger state for configured pulse time (for example 500 ms).
- Restore GPIO19 to idle state and return success.
