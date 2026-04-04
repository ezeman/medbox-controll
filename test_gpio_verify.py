#!/usr/bin/env python3
"""
GPIO Relay Verification Test.

Tests each GPIO pin individually to verify:
1. Current state of all pins
2. Which value (HIGH/LOW) triggers the relay
3. Which value (HIGH/LOW) is idle

Run: sudo .venv-relay-test/bin/python test_gpio_verify.py
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


def read_all():
    """Read current state of all relay GPIO pins."""
    print("\n=== Current GPIO Pin States ===")
    for slot, pin in SLOT_GPIO.items():
        line = GPIO(CHIP, pin, "in")
        val = line.read()
        line.close()
        state = "HIGH" if val else "LOW"
        print(f"  Slot {slot} (GPIO{pin:2d}) = {state}")
    print()


def set_all(value: bool, label: str):
    """Set all pins to a specific value and HOLD them."""
    lines = []
    print(f"\n=== Setting ALL pins to {label} (holding) ===")
    for slot, pin in SLOT_GPIO.items():
        line = GPIO(CHIP, pin, "out")
        line.write(value)
        lines.append((slot, pin, line))
        print(f"  Slot {slot} (GPIO{pin:2d}) -> {label}")
    print(f"\nAll pins set to {label}. Lines are HELD open.")
    return lines


def release_lines(lines):
    """Release all held lines."""
    for _, _, line in lines:
        line.close()
    print("  (Lines released)")


def test_single_pin_hold(slot: int, value: bool, label: str, hold_sec: float = 3.0):
    """Set a single pin and hold it for observation, then return to opposite."""
    pin = SLOT_GPIO[slot]
    idle = not value
    idle_label = "HIGH" if idle else "LOW"

    line = GPIO(CHIP, pin, "out")
    # First set to idle
    line.write(idle)
    print(f"  Slot {slot} (GPIO{pin}) = {idle_label} (idle)")
    time.sleep(0.5)

    # Now set to test value
    print(f"  Slot {slot} (GPIO{pin}) -> {label} ... ", end="", flush=True)
    line.write(value)
    print(f"HOLDING for {hold_sec}s - watch relay!")
    time.sleep(hold_sec)

    # Return to idle
    line.write(idle)
    print(f"  Slot {slot} (GPIO{pin}) -> {idle_label} (back to idle)")
    time.sleep(0.5)
    line.close()


def main():
    print("=" * 55)
    print("  GPIO Relay Verification Test")
    print("=" * 55)

    # Step 1: Read current states
    read_all()

    # Step 2: Set all HIGH and ask user
    input("Press Enter to set ALL pins HIGH (hold)...")
    lines = set_all(True, "HIGH")
    resp = input("\nAre relays OFF (idle) now? [y/n]: ").strip().lower()
    high_is_idle = resp == "y"
    release_lines(lines)
    time.sleep(0.3)

    # Step 3: Set all LOW and ask user
    input("\nPress Enter to set ALL pins LOW (hold)...")
    lines = set_all(False, "LOW")
    resp = input("\nAre relays OFF (idle) now? [y/n]: ").strip().lower()
    low_is_idle = resp == "y"
    release_lines(lines)
    time.sleep(0.3)

    # Step 4: Determine polarity
    print("\n=== Polarity Result ===")
    if high_is_idle and not low_is_idle:
        print("  -> ACTIVE-LOW confirmed (LOW=trigger, HIGH=idle)")
        print("  -> RELAY_ACTIVE_LOW=true is CORRECT")
        active_low = True
    elif low_is_idle and not high_is_idle:
        print("  -> ACTIVE-HIGH confirmed (HIGH=trigger, LOW=idle)")
        print("  -> RELAY_ACTIVE_LOW=false is NEEDED")
        active_low = False
    elif high_is_idle and low_is_idle:
        print("  -> Both states idle? Check wiring!")
        active_low = None
    else:
        print("  -> Both states trigger? Check wiring!")
        active_low = None

    if active_low is None:
        print("  Cannot determine polarity. Check hardware wiring.")
        sys.exit(1)

    # Step 5: Test individual slot pulse
    idle_val = True if active_low else False
    active_val = not idle_val
    active_label = "LOW" if active_low else "HIGH"
    idle_label = "HIGH" if active_low else "LOW"

    # Set all to idle first
    print(f"\n=== Setting all pins to idle ({idle_label}) ===")
    idle_lines = []
    for slot, pin in SLOT_GPIO.items():
        line = GPIO(CHIP, pin, "out")
        line.write(idle_val)
        idle_lines.append(line)
    print("  All pins at idle.")

    # Release for individual test
    for l in idle_lines:
        l.close()
    time.sleep(0.3)

    resp = input("\nTest individual slot pulse? [y/n]: ").strip().lower()
    if resp == "y":
        for slot in sorted(SLOT_GPIO.keys()):
            resp2 = input(f"\nPulse Slot {slot} (GPIO{SLOT_GPIO[slot]})? [y/n/q]: ").strip().lower()
            if resp2 == "q":
                break
            if resp2 == "y":
                test_single_pin_hold(slot, active_val, active_label, 2.0)
                resp3 = input(f"  Did Slot {slot} relay click ON then OFF? [y/n]: ").strip().lower()
                if resp3 == "y":
                    print(f"  Slot {slot} OK!")
                else:
                    print(f"  Slot {slot} FAILED - check wiring for GPIO{SLOT_GPIO[slot]}")

    # Final: set all to idle and hold
    print(f"\n=== Final: Setting all pins to idle ({idle_label}) and HOLDING ===")
    final_lines = set_all(idle_val, idle_label)
    input("\nAll pins at idle. Press Enter to release and exit...")
    release_lines(final_lines)

    print("\n=== Summary ===")
    print(f"  Active-Low: {active_low}")
    print(f"  Idle value: {idle_label}")
    print(f"  Trigger value: {active_label}")
    print(f"  RELAY_ACTIVE_LOW should be: {'true' if active_low else 'false'}")
    print(f"  Boot config gpio= should use: {'dh' if active_low else 'dl'}")
    print()


if __name__ == "__main__":
    main()
