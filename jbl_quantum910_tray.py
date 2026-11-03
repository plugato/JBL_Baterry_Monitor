#!/usr/bin/env python3
"""
JBL Quantum910 - Tray Battery Monitor (Linux)

- Shows headset battery percentage in the system tray (AppIndicator).
- Reads battery primarily via hidraw (least intrusive).
- Falls back to pyusb if hidraw is unavailable.

Battery format confirmed in this repo:
  [Report ID, Battery%] => 0x08 <0..100>
"""

from __future__ import annotations

import argparse
import errno
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

__version__ = "1.2.0"

VENDOR_ID_HEX = "0ecb"
PRODUCT_ID_HEX = "2088"
VENDOR_ID = int(VENDOR_ID_HEX, 16)
PRODUCT_ID = int(PRODUCT_ID_HEX, 16)
HID_INTERFACE = 3
HID_SYSFS_BASE = "/sys/bus/hid/devices"


def _import_appindicator():
    """
    AppIndicator naming varies by distro:
    - Ubuntu/Debian often provide AppIndicator3
    - Some distros provide AyatanaAppIndicator3
    """
    try:
        import gi  # type: ignore

        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk, GLib  # type: ignore

        try:
            gi.require_version("AppIndicator3", "0.1")
            from gi.repository import AppIndicator3 as AppIndicator  # type: ignore
        except Exception:
            gi.require_version("AyatanaAppIndicator3", "0.1")
            from gi.repository import AyatanaAppIndicator3 as AppIndicator  # type: ignore

        return Gtk, GLib, AppIndicator
    except Exception as e:
        print("Erro: dependências do tray não encontradas (PyGObject/AppIndicator).", file=sys.stderr)
        print(f"Detalhe: {e}", file=sys.stderr)
        print("\nPython em uso:", file=sys.stderr)
        print(f"  Executável: {sys.executable}", file=sys.stderr)
        print(f"  Versão: {sys.version.split()[0]}", file=sys.stderr)
        print("\nInstale (Debian/Ubuntu):", file=sys.stderr)
        print("  sudo apt install -y python3-gi gir1.2-ayatanaappindicator3-0.1", file=sys.stderr)
        print("  # ou: gir1.2-appindicator3-0.1", file=sys.stderr)
        print("\nDica:", file=sys.stderr)
        print("  Se você usa pyenv/conda/venv, rode com o Python do sistema:", file=sys.stderr)
        print("    /usr/bin/python3 ./jbl_quantum910_tray.py", file=sys.stderr)
        sys.exit(1)


def _read_uevent(path: str) -> dict[str, str]:
    values: dict[str, str] = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            key, sep, value = line.strip().partition("=")
            if sep:
                values[key] = value
    return values


def find_hidraw_device(base: str = HID_SYSFS_BASE, dev_dir: str = "/dev") -> Optional[str]:
    """
    Find the hidraw node of the JBL Quantum910 HID interface.

    HID devices in sysfs expose `uevent` with HID_ID=<bus>:<vendor>:<product>
    (no idVendor/idProduct files). The headset exposes several HID interfaces;
    the battery reports come from interface 3 (HID_PHYS ends with /input3),
    so that one is preferred. Never falls back to an unrelated device.
    """
    if not os.path.isdir(base):
        return None

    candidates: list[tuple[int, str]] = []
    for device_dir in sorted(os.listdir(base)):
        full = os.path.join(base, device_dir)
        try:
            uevent = _read_uevent(os.path.join(full, "uevent"))
            parts = uevent.get("HID_ID", "").lower().split(":")
            if len(parts) != 3 or int(parts[1], 16) != VENDOR_ID or int(parts[2], 16) != PRODUCT_ID:
                continue
            hidraw_path = os.path.join(full, "hidraw")
            if not os.path.isdir(hidraw_path):
                continue
            preferred = uevent.get("HID_PHYS", "").endswith(f"/input{HID_INTERFACE}")
            for entry in sorted(os.listdir(hidraw_path)):
                if entry.startswith("hidraw"):
                    candidates.append((0 if preferred else 1, os.path.join(dev_dir, entry)))
        except (OSError, ValueError):
            continue

    for _, dev in sorted(candidates):
        if os.path.exists(dev):
            return dev
    return None


def parse_battery_from_packet(packet: bytes) -> Optional[int]:
    """Parse battery percent from a single packet (strict known pattern)."""
    if len(packet) >= 2 and packet[0] == 0x08:
        b = packet[1]
        if 0 <= b <= 100:
            return int(b)
    return None


def parse_mute_from_packet(packet: bytes) -> Optional[tuple[bool, bool]]:
    """
    Parse mute status from a packet (Report ID 0x2f).
    - 0x2f 0x02 = toggle mute (botão pressionado) -> retorna (True, True) = toggle
    - 0x2f 0x00 = estado desmutado -> retorna (False, False) = desmutado
    Returns (is_toggle, is_muted) or None if not a mute packet.
    """
    if len(packet) >= 2 and packet[0] == 0x2f:
        if packet[1] == 0x02:
            return (True, True)  # Toggle - precisa alternar estado
        elif packet[1] == 0x00:
            return (False, False)  # Estado desmutado
    return None


def _log(msg: str) -> None:
    # Journald/systemd friendly: timestamp + flush
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


@dataclass
class BatterySample:
    percent: int
    source: str
    raw_hex: str
    ts: float


CACHE_SOURCE = "cache"


def _cache_path() -> str:
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base, "jbl-quantum910-tray", "last_battery.json")


def save_cached_battery(sample: BatterySample, path: Optional[str] = None) -> None:
    """
    Persist the last real reading. The headset only sends battery reports
    occasionally and does not answer GET_REPORT with real data, so without this
    a restart shows no value until the next spontaneous report.
    """
    path = path or _cache_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"percent": sample.percent, "ts": sample.ts, "raw_hex": sample.raw_hex}, f)
        os.replace(tmp, path)
    except OSError as e:
        _log(f"Erro ao salvar cache da bateria: {e}")


def load_cached_battery(path: Optional[str] = None) -> Optional[BatterySample]:
    try:
        with open(path or _cache_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        percent = int(data["percent"])
        if not 0 <= percent <= 100:
            return None
        return BatterySample(percent=percent, source=CACHE_SOURCE, raw_hex=str(data.get("raw_hex", "")), ts=float(data["ts"]))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _format_age(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds / 60:.0f}min"
    return f"{seconds / 3600:.1f}h"


@dataclass
class MuteSample:
    is_toggle: bool  # True se é toggle (0x02), False se é estado (0x00)
    muted: bool  # True se mutado, False se desmutado
    source: str
    raw_hex: str
    ts: float


def _hex(data: bytes) -> str:
    return " ".join(f"{b:02x}" for b in data[:8])


def _parse_packets(packets, source: str) -> tuple[Optional[BatterySample], Optional[MuteSample]]:
    """Return the latest battery and mute samples found in a sequence of packets."""
    last_battery: Optional[BatterySample] = None
    last_mute: Optional[MuteSample] = None
    for data in packets:
        percent = parse_battery_from_packet(data)
        if percent is not None:
            last_battery = BatterySample(percent=percent, source=source, raw_hex=_hex(data), ts=time.time())
        mute_info = parse_mute_from_packet(data)
        if mute_info is not None:
            is_toggle, is_muted = mute_info
            last_mute = MuteSample(
                is_toggle=is_toggle, muted=is_muted, source=source, raw_hex=_hex(data), ts=time.time()
            )
    return last_battery, last_mute


class HidrawBatteryReader:
    MAX_PACKETS = 32

    def __init__(self, path: str):
        self.path = path
        self._fd: Optional[int] = None
        self.last_error: Optional[str] = None

    def close(self) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
        self._fd = None

    def poll_all(self) -> tuple[Optional[BatterySample], Optional[MuteSample]]:
        """Drain pending packets (non-blocking) and return the latest battery/mute samples."""
        try:
            if self._fd is None:
                self._fd = os.open(self.path, os.O_RDONLY | os.O_NONBLOCK)
        except OSError as e:
            self.last_error = f"{self.path}: {e.strerror}"
            self.close()
            return None, None

        packets = []
        for _ in range(self.MAX_PACKETS):
            try:
                data = os.read(self._fd, 64)
            except OSError as e:
                if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                    break
                # Device went away / permission error / etc. Reopen next time.
                self.last_error = f"{self.path}: {e.strerror}"
                self.close()
                break
            if not data:
                break
            packets.append(data)

        if packets:
            self.last_error = None
        return _parse_packets(packets, f"hidraw:{self.path}")


class PyUsbBatteryReader:
    """
    PyUSB reader mirroring the known-good logic from `jbl_battery_simple.py`:
    - find device by VID/PID
    - (best-effort) detach kernel driver on interface 3
    - claim interface 3
    - read endpoint device[0][(3,0)][0]

    Reads use short timeouts because they run inside the GTK main loop.
    The kernel driver is re-attached on close().
    """

    MAX_PACKETS = 8

    def __init__(self, timeout_ms: int = 200, drain_timeout_ms: int = 20):
        self.timeout_ms = timeout_ms
        self.drain_timeout_ms = drain_timeout_ms
        self._usb_core = None
        self._usb_util = None
        self._device = None
        self._endpoint = None
        self._claimed = False
        self._detached = False
        self.last_error: Optional[str] = None

    def close(self) -> None:
        dev = self._device
        if dev is not None and self._usb_util is not None:
            if self._claimed:
                try:
                    self._usb_util.release_interface(dev, HID_INTERFACE)
                except Exception:
                    pass
            if self._detached:
                try:
                    dev.attach_kernel_driver(HID_INTERFACE)
                except Exception:
                    pass
            try:
                self._usb_util.dispose_resources(dev)
            except Exception:
                pass
        self._device = None
        self._endpoint = None
        self._claimed = False
        self._detached = False

    def _ensure_ready(self) -> bool:
        if self._device is not None and self._endpoint is not None:
            return True
        try:
            import usb.core  # type: ignore
            import usb.util  # type: ignore
        except ImportError:
            self.last_error = "pyusb não instalado (sudo apt install python3-usb)"
            return False

        self._usb_core, self._usb_util = usb.core, usb.util
        try:
            dev = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID)
            if dev is None:
                self.last_error = "Dispositivo não encontrado"
                return False
            self._device = dev

            try:
                if dev.is_kernel_driver_active(HID_INTERFACE):
                    dev.detach_kernel_driver(HID_INTERFACE)
                    self._detached = True
            except Exception:
                pass

            try:
                usb.util.claim_interface(dev, HID_INTERFACE)
            except Exception as e:
                self.last_error = f"Erro ao reivindicar interface {HID_INTERFACE}: {e}"
                self.close()
                return False
            self._claimed = True

            self._endpoint = dev[0][(HID_INTERFACE, 0)][0]
            self.last_error = None
            return True
        except Exception as e:
            self.last_error = f"Falha ao inicializar pyusb: {e}"
            self.close()
            return False

    def _is_timeout(self, e: Exception) -> bool:
        timeout_cls = getattr(self._usb_core, "USBTimeoutError", None)
        if timeout_cls is not None and isinstance(e, timeout_cls):
            return True
        return getattr(e, "errno", None) == errno.ETIMEDOUT

    def poll_all(self) -> tuple[Optional[BatterySample], Optional[MuteSample]]:
        """Read pending packets until a timeout and return the latest battery/mute samples."""
        if not self._ensure_ready():
            return None, None

        dev, ep = self._device, self._endpoint
        packets = []
        for i in range(self.MAX_PACKETS):
            timeout_ms = self.timeout_ms if i == 0 else self.drain_timeout_ms
            try:
                data = dev.read(ep.bEndpointAddress, ep.wMaxPacketSize, timeout_ms)
            except Exception as e:
                if not self._is_timeout(e):
                    # Device unplugged / reset: re-init next time.
                    self.last_error = str(e)
                    self.close()
                break
            packets.append(bytes(data))

        return _parse_packets(packets, "pyusb")


class BatteryTrayApp:
    HIDRAW_RESCAN_SECONDS = 10.0

    def __init__(self, refresh_seconds: float, prefer_pyusb: bool):
        self.refresh_seconds = max(0.2, refresh_seconds)
        self.prefer_pyusb = prefer_pyusb

        self.Gtk, self.GLib, self.AppIndicator = _import_appindicator()

        # Start from the last saved reading so a restart doesn't show "?" until
        # the headset happens to send a new battery report.
        self.last_sample: Optional[BatterySample] = load_cached_battery()
        self.last_mute_sample: Optional[MuteSample] = None
        self._last_label: Optional[str] = None
        self._last_icon: Optional[str] = None
        self._last_logged_error: Optional[str] = None
        self._last_logged_percent: Optional[int] = None
        self._is_muted: bool = False

        self.hidraw_reader: Optional[HidrawBatteryReader] = None
        self._last_hidraw_scan = 0.0
        self._rescan_hidraw()
        self.pyusb_reader = PyUsbBatteryReader()

        self.indicator = self.AppIndicator.Indicator.new(
            "jbl-quantum910-battery",
            "battery-missing-symbolic",
            self.AppIndicator.IndicatorCategory.HARDWARE,
        )
        self.indicator.set_status(self.AppIndicator.IndicatorStatus.ACTIVE)
        try:
            self.indicator.set_title("JBL Quantum910 Battery")
        except Exception:
            pass

        self.menu = self._build_menu()
        self.indicator.set_menu(self.menu)

        self._render()
        hidraw = self.hidraw_reader.path if self.hidraw_reader else None
        _log(f"Tray iniciado (v{__version__}). prefer_pyusb={self.prefer_pyusb} hidraw={hidraw!s}")
        if self.last_sample is not None:
            age = _format_age(max(0.0, time.time() - self.last_sample.ts))
            _log(f"Último valor salvo: {self.last_sample.percent}% (há {age})")

        self.GLib.timeout_add(int(self.refresh_seconds * 1000), self._tick)

    def _build_menu(self):
        menu = self.Gtk.Menu()

        item_refresh = self.Gtk.MenuItem(label="Atualizar agora")
        item_refresh.connect("activate", lambda *_: self._tick())
        menu.append(item_refresh)

        item_sep = self.Gtk.SeparatorMenuItem()
        menu.append(item_sep)

        item_quit = self.Gtk.MenuItem(label="Sair")
        item_quit.connect("activate", lambda *_: self._quit())
        menu.append(item_quit)

        menu.show_all()
        return menu

    def _quit(self):
        try:
            if self.hidraw_reader:
                self.hidraw_reader.close()
            self.pyusb_reader.close()
        finally:
            self.Gtk.main_quit()
        return False  # remove GLib signal source

    def _rescan_hidraw(self) -> None:
        """(Re)discover the hidraw node, e.g. when the headset is plugged in after startup."""
        self._last_hidraw_scan = time.monotonic()
        path = find_hidraw_device()
        if self.hidraw_reader is not None and self.hidraw_reader.path == path:
            return
        if self.hidraw_reader is not None:
            self.hidraw_reader.close()
        self.hidraw_reader = HidrawBatteryReader(path) if path else None
        if path:
            _log(f"hidraw detectado: {path}")

    def _readers(self):
        readers = [self.hidraw_reader, self.pyusb_reader]
        if self.prefer_pyusb:
            readers.reverse()
        return [r for r in readers if r is not None]

    def _last_error(self) -> Optional[str]:
        """Return an error only when no reader is healthy (one working source is enough)."""
        errors = [reader.last_error for reader in self._readers()]
        if not errors or not all(errors):
            return None
        return errors[0]

    def _read_all_once(self) -> tuple[Optional[BatterySample], Optional[MuteSample]]:
        """
        Read battery and mute in a single pass per reader, so mute packets are not
        discarded by a separate battery-only read.
        """
        hidraw_broken = self.hidraw_reader is None or self.hidraw_reader.last_error is not None
        if hidraw_broken and time.monotonic() - self._last_hidraw_scan >= self.HIDRAW_RESCAN_SECONDS:
            self._rescan_hidraw()

        battery_sample: Optional[BatterySample] = None
        mute_sample: Optional[MuteSample] = None
        for reader in self._readers():
            battery, mute = reader.poll_all()
            battery_sample = battery_sample or battery
            mute_sample = mute_sample or mute
            if battery_sample is not None:
                break
        return battery_sample, mute_sample

    def _tick(self):
        battery_sample, mute_sample = self._read_all_once()

        if battery_sample is not None:
            self.last_sample = battery_sample
            if self._last_logged_percent != battery_sample.percent:
                _log(f"Bateria: {battery_sample.percent}% (fonte={battery_sample.source}, dados={battery_sample.raw_hex})")
                self._last_logged_percent = battery_sample.percent
                self._last_logged_error = None
                save_cached_battery(battery_sample)
        else:
            err = self._last_error()
            if err and err != self._last_logged_error:
                _log(f"Sem leitura. Erro: {err}")
                self._last_logged_error = err

        if mute_sample is not None:
            self.last_mute_sample = mute_sample
            if mute_sample.is_toggle:
                # 0x2f 0x02 é um toggle - alterna o estado
                self._is_muted = not self._is_muted
                origem = "toggle detectado"
            else:
                # 0x2f 0x00 = estado desmutado
                self._is_muted = False
                origem = "estado recebido"
            status = "🔇 MUTADO" if self._is_muted else "🎤 DESMUTADO"
            _log(f"Microfone {status} ({origem}, fonte={mute_sample.source}, dados={mute_sample.raw_hex})")

        self._render()
        return True  # keep timer

    def _render(self):
        percent = self.last_sample.percent if self.last_sample else None
        icon = battery_icon_name(percent, self._is_muted)
        if icon != self._last_icon:
            self.indicator.set_icon_full(icon, "JBL Quantum910 Battery")
            self._last_icon = icon

        err = self._last_error()
        if percent is not None:
            label = f"{percent}%{' 🔇' if self._is_muted else ''}"
        elif err:
            label = "ERR"
        else:
            label = "--%"

        if label != self._last_label:
            try:
                self.indicator.set_label(label, "")
                self._last_label = label
            except Exception as e:
                # Some tray implementations don't support set_label
                _log(f"Erro ao atualizar label: {e}")

        mute_status = "🔇 MUTADO" if self._is_muted else "🎤 Ativo"
        if self.last_sample:
            age = _format_age(max(0.0, time.time() - self.last_sample.ts))
            cached = " (último valor salvo, aguardando nova leitura)" if self.last_sample.source == CACHE_SOURCE else ""
            tip = (
                f"JBL Quantum910: {self.last_sample.percent}%{cached}\nMicrofone: {mute_status}\n"
                f"Fonte: {self.last_sample.source}\nAtualizado há: {age}\nDados: {self.last_sample.raw_hex}"
            )
        else:
            extra = f"\nErro: {err}" if err else ""
            tip = (
                f"JBL Quantum910: sem leitura ainda\nMicrofone: {mute_status}{extra}\n"
                "Dica: use o fone (volume/botões) para gerar tráfego."
            )
        # Some implementations show tooltip via icon description:
        try:
            self.indicator.set_icon_desc(tip)
        except Exception:
            pass

    def run(self):
        # Python signal handlers don't run while Gtk.main() blocks in C; let GLib handle them.
        import signal

        for sig in (signal.SIGINT, signal.SIGTERM):
            self.GLib.unix_signal_add(self.GLib.PRIORITY_DEFAULT, sig, self._quit)
        self.Gtk.main()


def battery_icon_name(percent: Optional[int], is_muted: bool = False) -> str:
    """Get icon name based on battery level and mute status."""
    if is_muted:
        return "microphone-sensitivity-muted-symbolic"
    if percent is None:
        return "battery-missing-symbolic"
    if percent >= 95:
        return "battery-full-symbolic"
    if percent >= 75:
        return "battery-good-symbolic"
    if percent >= 40:
        return "battery-medium-symbolic"
    if percent >= 15:
        return "battery-low-symbolic"
    return "battery-caution-symbolic"


def main() -> int:
    parser = argparse.ArgumentParser(description="JBL Quantum910 tray battery monitor (AppIndicator)")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--refresh", type=float, default=1.0, help="Intervalo de atualização em segundos (default: 1.0)")
    parser.add_argument(
        "--prefer-pyusb",
        action="store_true",
        help="(padrão) Tenta pyusb primeiro",
    )
    parser.add_argument(
        "--prefer-hidraw",
        action="store_true",
        help="Prefere hidraw primeiro (pode funcionar sem 'claim interface')",
    )
    parser.add_argument(
        "--pyusb-detach-kernel",
        action="store_true",
        help="(compat) Ignorado: o comportamento padrão já tenta detach best-effort como no jbl_battery_simple.py",
    )
    args = parser.parse_args()

    app = BatteryTrayApp(
        refresh_seconds=args.refresh,
        prefer_pyusb=(not args.prefer_hidraw),
    )
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
