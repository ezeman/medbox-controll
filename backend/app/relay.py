import os
import shutil
import subprocess
from pathlib import Path
from time import sleep
from time import monotonic
from contextlib import suppress

import httpx

try:
    from periphery import GPIO
except ImportError:  # pragma: no cover - dependency/runtime fallback
    GPIO = None


SLOT_GPIO_MAP = {
    1: 7,
    2: 12,
    3: 16,
    4: 11,
    5: 23,
    6: 24,
    7: 25,
    8: 8,
}


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


class GpioRelayController:
    """Persistent GPIO relay controller.

    Lines are held open for the lifetime of the process so that idle
    state (HIGH for active-low boards) is actively driven at all times.
    Releasing lines would let the Pi's internal pull resistors take over,
    which on many pins defaults to LOW — triggering active-low relays.
    """

    def __init__(self) -> None:
        self.chip_path = os.getenv("GPIO_CHIP", "/dev/gpiochip0")
        self.pulse_ms = max(int(os.getenv("RELAY_PULSE_MS", "500")), 50)
        self.min_gap_ms = max(int(os.getenv("RELAY_MIN_GAP_MS", "2500")), 0)
        self.active_low = _env_flag("RELAY_ACTIVE_LOW", True)
        self.idle_input = _env_flag("RELAY_IDLE_INPUT", True)
        self.raspi_gpio_bin = shutil.which("raspi-gpio")
        self._lines: dict[int, "GPIO"] = {}
        self._last_pulse_at: dict[int, float] = {}
        self._setup_error: str | None = None

    @property
    def idle_value(self) -> bool:
        return True if self.active_low else False

    @property
    def active_value(self) -> bool:
        return not self.idle_value

    @property
    def pulse_seconds(self) -> float:
        return self.pulse_ms / 1000

    def setup(self) -> None:
        if self._lines:
            return

        if self.raspi_gpio_bin and self.idle_input:
            try:
                for gpio_pin in SLOT_GPIO_MAP.values():
                    self._run_raspi_gpio(gpio_pin, "ip")
            except Exception as exc:
                self._setup_error = str(exc)
                raise
            self._setup_error = None
            return

        if GPIO is None:
            self._setup_error = "python-periphery is not installed"
            raise RuntimeError(self._setup_error)

        if not Path(self.chip_path).exists():
            self._setup_error = f"GPIO chip not found: {self.chip_path}"
            raise FileNotFoundError(self._setup_error)

        if self.idle_input:
            # Open-drain style: keep idle as input so 5V relay boards can pull-up safely.
            try:
                for gpio_pin in SLOT_GPIO_MAP.values():
                    with suppress(Exception):
                        GPIO(self.chip_path, gpio_pin, "in").close()
            except Exception as exc:
                self._setup_error = str(exc)
                raise
            self._setup_error = None
            return

        opened: dict[int, "GPIO"] = {}
        try:
            for slot_id, gpio_pin in SLOT_GPIO_MAP.items():
                line = GPIO(self.chip_path, gpio_pin, "out")
                line.write(self.idle_value)
                opened[slot_id] = line
        except Exception as exc:
            self._setup_error = str(exc)
            for line in opened.values():
                try:
                    line.close()
                except Exception:
                    pass
            raise

        self._setup_error = None
        self._lines = opened

    def _set_idle_input(self, slot_id: int) -> None:
        gpio_pin = SLOT_GPIO_MAP[slot_id]
        if self.raspi_gpio_bin:
            self._run_raspi_gpio(gpio_pin, "ip")
            return
        line = GPIO(self.chip_path, gpio_pin, "in")
        line.close()

    def _set_active_output(self, slot_id: int) -> None:
        gpio_pin = SLOT_GPIO_MAP[slot_id]
        if self.raspi_gpio_bin:
            # User-required behavior: relay ON via output drive-low.
            if self.active_low:
                self._run_raspi_gpio(gpio_pin, "op", "dl")
            else:
                self._run_raspi_gpio(gpio_pin, "op", "dh")
            return
        line = GPIO(self.chip_path, gpio_pin, "out")
        line.write(False)
        line.close()

    def _run_raspi_gpio(self, gpio_pin: int, *args: str) -> None:
        if not self.raspi_gpio_bin:
            raise RuntimeError("raspi-gpio not available")
        command = [self.raspi_gpio_bin, "set", str(gpio_pin), *args]
        subprocess.run(command, check=True, capture_output=True, text=True)

    def _ensure_line(self, slot_id: int) -> "GPIO":
        if slot_id not in SLOT_GPIO_MAP:
            raise ValueError(f"No GPIO mapping configured for slot {slot_id}")
        if not self._lines:
            self.setup()
        return self._lines[slot_id]

    def pulse_slot(self, slot_id: int) -> str:
        now = monotonic()
        if self.min_gap_ms > 0:
            last = self._last_pulse_at.get(slot_id)
            if last is not None and (now - last) < (self.min_gap_ms / 1000):
                return f"GPIO{SLOT_GPIO_MAP[slot_id]} pulse skipped anti-chatter ({self.min_gap_ms}ms)"

        if self.idle_input and self.active_low:
            self._set_active_output(slot_id)
            try:
                sleep(self.pulse_seconds)
            finally:
                self._set_idle_input(slot_id)
            self._last_pulse_at[slot_id] = monotonic()
            return f"GPIO{SLOT_GPIO_MAP[slot_id]} pulsed {self.pulse_ms}ms (open-drain emulation)"

        line = self._ensure_line(slot_id)
        line.write(self.active_value)
        try:
            sleep(self.pulse_seconds)
        finally:
            line.write(self.idle_value)
        self._last_pulse_at[slot_id] = monotonic()
        return f"GPIO{SLOT_GPIO_MAP[slot_id]} pulsed {self.pulse_ms}ms (held)"

    def close_slot(self, slot_id: int) -> str:
        if self.idle_input and self.active_low:
            self._set_idle_input(slot_id)
            return f"GPIO{SLOT_GPIO_MAP[slot_id]} set to idle input (open-drain emulation)"

        line = self._ensure_line(slot_id)
        line.write(self.idle_value)
        return f"GPIO{SLOT_GPIO_MAP[slot_id]} set to idle (held)"

    def status_detail(self) -> str:
        if self.idle_input:
            return f"GPIO open-drain emulation ready on {self.chip_path}"
        if self._lines:
            return f"GPIO ready, {len(self._lines)} lines held on {self.chip_path}"
        return self._setup_error or f"GPIO not initialized on {self.chip_path}"

    def close(self) -> None:
        if self.raspi_gpio_bin and self.idle_input:
            for gpio_pin in SLOT_GPIO_MAP.values():
                with suppress(Exception):
                    self._run_raspi_gpio(gpio_pin, "ip")
            return

        for line in self._lines.values():
            try:
                line.write(self.idle_value)
            except Exception:
                pass
            try:
                line.close()
            except Exception:
                pass
        self._lines.clear()


GPIO_RELAY_CONTROLLER = GpioRelayController()
RELAY_MODE = os.getenv("RELAY_MODE", "gpio").strip().lower()
RELAY_API_URL = os.getenv("RELAY_API_URL", "")


def initialize_gpio_relay() -> None:
    if RELAY_MODE in {"gpio", "auto"}:
        GPIO_RELAY_CONTROLLER.setup()


def shutdown_gpio_relay() -> None:
    GPIO_RELAY_CONTROLLER.close()


def _send_http_relay_open(slot_id: int) -> tuple[str, str | None]:
    if not RELAY_API_URL:
        return "simulated", "RELAY_API_URL not configured"

    payload = {"slot_id": slot_id, "action": "open"}
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.post(RELAY_API_URL, json=payload)
            response.raise_for_status()
        return "ok", None
    except Exception as exc:
        return "failed", str(exc)


def send_relay_open(slot_id: int) -> tuple[str, str | None]:
    if slot_id not in SLOT_GPIO_MAP:
        return "failed", f"No GPIO mapping configured for slot {slot_id}"

    if RELAY_MODE == "http":
        return _send_http_relay_open(slot_id)

    try:
        detail = GPIO_RELAY_CONTROLLER.pulse_slot(slot_id)
        return "ok", detail
    except Exception as exc:
        gpio_detail = str(exc) or GPIO_RELAY_CONTROLLER.status_detail()
        if RELAY_MODE == "auto" and RELAY_API_URL:
            http_result, http_detail = _send_http_relay_open(slot_id)
            if http_result == "ok":
                return http_result, http_detail
        return "simulated", gpio_detail


def send_relay_close(slot_id: int) -> tuple[str, str | None]:
    if slot_id not in SLOT_GPIO_MAP:
        return "failed", f"No GPIO mapping configured for slot {slot_id}"

    if RELAY_MODE == "http":
        return "simulated", "HTTP relay mode does not support direct close"

    try:
        detail = GPIO_RELAY_CONTROLLER.close_slot(slot_id)
        return "ok", detail
    except Exception as exc:
        return "simulated", str(exc) or GPIO_RELAY_CONTROLLER.status_detail()