# Relay Controller Notes

This cabinet now drives relays directly from Linux GPIO on the host machine.

## Fixed Slot To GPIO Mapping

| Slot No. | GPIO |
|---|---:|
| 1 | GPIO7 |
| 2 | GPIO12 |
| 3 | GPIO16 |
| 4 | GPIO20 |
| 5 | GPIO23 |
| 6 | GPIO24 |
| 7 | GPIO25 |
| 8 | GPIO8 |

Logic convention:
- Backend resolves `slot_id -> GPIO` directly by this table.
- Default trigger mode is active-low (`LOW` = relay on, `HIGH` = idle).
- Default pulse time is `500 ms` and is configurable with `RELAY_PULSE_MS`.

## Runtime Configuration

Backend env vars:

- `RELAY_MODE=gpio` to use direct GPIO output.
- `GPIO_CHIP=/dev/gpiochip0` for the Linux gpiochip device path.
- `RELAY_PULSE_MS=500` for trigger pulse width.
- `RELAY_ACTIVE_LOW=true` to use active-low relay triggering.
- `RELAY_IDLE_INPUT=true` to emulate open-drain output (idle=input, trigger=output-low) for relay boards that do not accept 3.3V HIGH as idle.
- `RELAY_MODE=auto` to try GPIO first and fall back to `RELAY_API_URL`.
- `RELAY_MODE=http` to keep using an external relay controller over HTTP.

Docker Compose maps the host gpiochip device into the backend container so the API can drive the lines directly.

## Electrical Notes

- Verify the relay board input channel matches the slot mapping before energizing doors.
- Use external power for relay coils and share ground with the host GPIO controller.
- If the relay board is not 3.3V compatible, add a driver stage or optocoupler board.
- Confirm whether the board is active-low or active-high before first live test.

## Expected Open Behavior

When the API opens slot `4`, backend should:

- Resolve slot `4 -> GPIO20`.
- Drive GPIO20 to the active state for `RELAY_PULSE_MS`.
- Restore GPIO20 to idle state and keep the line configured as output.
