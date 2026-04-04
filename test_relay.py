#!/usr/bin/env python3
"""
Interactive relay GPIO test script.
Run from the host (not inside Docker) to test each slot relay directly.

Usage:
    sudo .venv-relay-test/bin/python test_relay.py
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

PULSE_SEC = 0.5


def read_pin(pin: int) -> str:
    line = GPIO(CHIP, pin, "in")
    try:
        val = line.read()
    finally:
        line.close()
    return "HIGH" if val else "LOW"


def write_pin(pin: int, value: bool) -> None:
    line = GPIO(CHIP, pin, "out")
    try:
        line.write(value)
    finally:
        line.close()


def all_low():
    print("\n--- Setting ALL pins LOW ---")
    for slot, pin in SLOT_GPIO.items():
        write_pin(pin, False)
        print(f"  Slot {slot} (GPIO{pin}) -> LOW")
    print("Done.\n")


def all_high():
    print("\n--- Setting ALL pins HIGH ---")
    for slot, pin in SLOT_GPIO.items():
        write_pin(pin, True)
        print(f"  Slot {slot} (GPIO{pin}) -> HIGH")
    print("Done.\n")


def status():
    print("\n--- Current GPIO status ---")
    for slot, pin in SLOT_GPIO.items():
        val = read_pin(pin)
        print(f"  Slot {slot} (GPIO{pin}) = {val}")
    print()


def pulse_slot(slot: int, active_high: bool):
    pin = SLOT_GPIO[slot]
    active = True if active_high else False
    idle = not active
    label = "HIGH" if active else "LOW"

    print(f"\n--- Pulse Slot {slot} (GPIO{pin}) -> {label} for {PULSE_SEC}s ---")
    write_pin(pin, active)
    print(f"  GPIO{pin} = {label}  (relay should TRIGGER now)")
    time.sleep(PULSE_SEC)
    write_pin(pin, idle)
    idle_label = "HIGH" if idle else "LOW"
    print(f"  GPIO{pin} = {idle_label}  (relay should RELEASE now)")
    print("Done.\n")


def set_slot(slot: int, high: bool):
    pin = SLOT_GPIO[slot]
    label = "HIGH" if high else "LOW"
    write_pin(pin, high)
    print(f"  Slot {slot} (GPIO{pin}) -> {label}")


def menu():
    print("=" * 50)
    print("  Relay GPIO Test")
    print("=" * 50)
    print("  s        = Show status of all pins")
    print("  l        = Set ALL pins LOW")
    print("  h        = Set ALL pins HIGH")
    print("  o <slot>  = Pulse slot (active-HIGH then LOW)")
    print("  O <slot>  = Pulse slot (active-LOW then HIGH)")
    print("  sh <slot> = Set single slot HIGH")
    print("  sl <slot> = Set single slot LOW")
    print("  t <sec>   = Change pulse duration (current: {:.2f}s)".format(PULSE_SEC))
    print("  q        = Quit (sets all LOW before exit)")
    print("=" * 50)


def main():
    global PULSE_SEC

    menu()
    status()

    while True:
        try:
            raw = input("relay> ").strip()
        except (EOFError, KeyboardInterrupt):
            raw = "q"

        if not raw:
            continue

        parts = raw.split()
        cmd = parts[0].lower()

        if cmd == "q":
            all_low()
            print("Exiting.")
            break
        elif cmd == "s":
            status()
        elif cmd == "l":
            all_low()
        elif cmd == "h":
            all_high()
        elif cmd == "o" and len(parts) == 2:
            try:
                slot = int(parts[1])
                if slot not in SLOT_GPIO:
                    print(f"  Invalid slot {slot}. Valid: 1-8")
                    continue
                pulse_slot(slot, active_high=True)
            except ValueError:
                print("  Usage: o <slot_number>")
        elif cmd.upper() == "O" and len(parts) == 2 and parts[0] == "O":
            try:
                slot = int(parts[1])
                if slot not in SLOT_GPIO:
                    print(f"  Invalid slot {slot}. Valid: 1-8")
                    continue
                pulse_slot(slot, active_high=False)
            except ValueError:
                print("  Usage: O <slot_number>")
        elif cmd == "sh" and len(parts) == 2:
            try:
                slot = int(parts[1])
                if slot not in SLOT_GPIO:
                    print(f"  Invalid slot {slot}. Valid: 1-8")
                    continue
                set_slot(slot, True)
            except ValueError:
                print("  Usage: sh <slot_number>")
        elif cmd == "sl" and len(parts) == 2:
            try:
                slot = int(parts[1])
                if slot not in SLOT_GPIO:
                    print(f"  Invalid slot {slot}. Valid: 1-8")
                    continue
                set_slot(slot, False)
            except ValueError:
                print("  Usage: sl <slot_number>")
        elif cmd == "t" and len(parts) == 2:
            try:
                PULSE_SEC = max(float(parts[1]), 0.05)
                print(f"  Pulse duration set to {PULSE_SEC:.2f}s")
            except ValueError:
                print("  Usage: t <seconds>")
        else:
            menu()


if __name__ == "__main__":
    main()
