#!/usr/bin/env python3
"""
Non-interactive GPIO relay test.

Usage:
    sudo .venv-relay-test/bin/python test_auto.py [command]

Commands:
    status    - Read all pin states
    all_high  - Set all pins HIGH and hold (Ctrl+C to release)
    all_low   - Set all pins LOW and hold (Ctrl+C to release)
    pulse_low <slot>  - Pulse one slot LOW for 2s then back to HIGH
    pulse_high <slot> - Pulse one slot HIGH for 2s then back to LOW
    test_active_low   - Test all slots assuming active-low (idle=HIGH, trigger=LOW)
    test_active_high  - Test all slots assuming active-HIGH (idle=LOW, trigger=HIGH)
"""

import sys
import time
from periphery import GPIO

CHIP = "/dev/gpiochip0"

SLOT_GPIO = {
    1: 7,
    2: 12,
    3: 16,
    4: 20,
    5: 23,
    6: 24,
    7: 25,
    8: 8,
}


def status():
    print("=== GPIO Pin States ===")
    for slot, pin in sorted(SLOT_GPIO.items()):
        line = GPIO(CHIP, pin, "in")
        val = line.read()
        line.close()
        print(f"  Slot {slot} (GPIO{pin:2d}) = {'HIGH' if val else 'LOW'}")


def hold_all(value: bool):
    label = "HIGH" if value else "LOW"
    print(f"=== Setting ALL pins to {label} and HOLDING ===")
    lines = []
    for slot, pin in sorted(SLOT_GPIO.items()):
        line = GPIO(CHIP, pin, "out")
        line.write(value)
        lines.append(line)
        print(f"  Slot {slot} (GPIO{pin:2d}) -> {label}")
    print(f"\nHolding all at {label}. Press Ctrl+C to release and exit.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nReleasing...")
    finally:
        for l in lines:
            try:
                l.close()
            except Exception:
                pass
    print("Released.")


def pulse_single(slot: int, active_val: bool, duration: float = 2.0):
    pin = SLOT_GPIO[slot]
    idle_val = not active_val
    active_label = "HIGH" if active_val else "LOW"
    idle_label = "HIGH" if idle_val else "LOW"

    line = GPIO(CHIP, pin, "out")
    line.write(idle_val)
    print(f"Slot {slot} (GPIO{pin}) = {idle_label} (idle)")
    time.sleep(0.5)

    print(f"Slot {slot} (GPIO{pin}) -> {active_label} (TRIGGER) for {duration}s")
    line.write(active_val)
    time.sleep(duration)

    line.write(idle_val)
    print(f"Slot {slot} (GPIO{pin}) -> {idle_label} (idle)")
    time.sleep(0.3)
    line.close()
    print("Done.")


def test_all(active_low: bool):
    idle_val = True if active_low else False
    active_val = not idle_val
    mode = "ACTIVE-LOW" if active_low else "ACTIVE-HIGH"
    idle_label = "HIGH" if idle_val else "LOW"
    active_label = "HIGH" if active_val else "LOW"

    print(f"=== Testing all slots ({mode}) ===")
    print(f"  Idle = {idle_label}, Trigger = {active_label}")
    print()

    # First set all to idle and hold
    lines = {}
    for slot, pin in sorted(SLOT_GPIO.items()):
        line = GPIO(CHIP, pin, "out")
        line.write(idle_val)
        lines[slot] = line
    print(f"All pins set to {idle_label} (idle). Waiting 3s...")
    time.sleep(3)

    # Pulse each slot one by one
    for slot in sorted(SLOT_GPIO.keys()):
        pin = SLOT_GPIO[slot]
        line = lines[slot]
        print(f"\n--- Slot {slot} (GPIO{pin}) ---")
        print(f"  -> {active_label} (TRIGGER)")
        line.write(active_val)
        time.sleep(2)
        print(f"  -> {idle_label} (IDLE)")
        line.write(idle_val)
        time.sleep(1)

    print(f"\n=== Test complete. All pins at {idle_label} (idle). ===")
    print("Holding lines for 5s then releasing...")
    time.sleep(5)

    for line in lines.values():
        line.close()
    print("Released.")


def usage():
    print(__doc__)
    sys.exit(1)


def main():
    if len(sys.argv) < 2:
        usage()

    cmd = sys.argv[1]

    if cmd == "status":
        status()
    elif cmd == "all_high":
        hold_all(True)
    elif cmd == "all_low":
        hold_all(False)
    elif cmd == "pulse_low":
        slot = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        pulse_single(slot, False)
    elif cmd == "pulse_high":
        slot = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        pulse_single(slot, True)
    elif cmd == "test_active_low":
        test_all(active_low=True)
    elif cmd == "test_active_high":
        test_all(active_low=False)
    else:
        usage()


if __name__ == "__main__":
    main()
