import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import jbl_quantum910_tray as tray  # noqa: E402


def test_parse_battery_valid():
    assert tray.parse_battery_from_packet(bytes([0x08, 0x1E])) == 30
    assert tray.parse_battery_from_packet(bytes([0x08, 0x00, 0xFF])) == 0
    assert tray.parse_battery_from_packet(bytes([0x08, 100])) == 100


def test_parse_battery_invalid():
    assert tray.parse_battery_from_packet(b"") is None
    assert tray.parse_battery_from_packet(bytes([0x08])) is None
    assert tray.parse_battery_from_packet(bytes([0x08, 101])) is None
    assert tray.parse_battery_from_packet(bytes([0x09, 0x1E])) is None


def test_parse_mute():
    assert tray.parse_mute_from_packet(bytes([0x06, 0x01])) is True
    assert tray.parse_mute_from_packet(bytes([0x06, 0x00])) is False
    assert tray.parse_mute_from_packet(bytes([0x06, 0x05])) is None
    # 0x2f is just the button press/release, not the state
    assert tray.parse_mute_from_packet(bytes([0x2F, 0x02])) is None
    assert tray.parse_mute_from_packet(bytes([0x2F, 0x00])) is None


def test_parse_packets_keeps_latest_battery_and_mute():
    # Real button press sequence captured from the headset: press, state, release.
    packets = [bytes([0x08, 50]), bytes([0x2F, 0x02]), bytes([0x06, 0x01]), bytes([0x2F, 0x00]), bytes([0x08, 49])]
    battery, mute = tray._parse_packets(packets, "test")
    assert battery is not None and battery.percent == 49
    assert mute is not None and mute.muted and mute.raw_hex == "06 01"


def test_battery_icon_name():
    assert tray.battery_icon_name(None) == "battery-missing-symbolic"
    assert tray.battery_icon_name(100) == "battery-full-symbolic"
    assert tray.battery_icon_name(80) == "battery-good-symbolic"
    assert tray.battery_icon_name(50) == "battery-medium-symbolic"
    assert tray.battery_icon_name(20) == "battery-low-symbolic"
    assert tray.battery_icon_name(5) == "battery-caution-symbolic"
    assert tray.battery_icon_name(80, is_muted=True) == "microphone-sensitivity-muted-symbolic"


def _make_hid(base, name, hid_id, phys, hidraw):
    d = base / name
    (d / "hidraw" / hidraw).mkdir(parents=True)
    (d / "uevent").write_text(f"DRIVER=hid-generic\nHID_ID={hid_id}\nHID_PHYS={phys}\n")


def test_find_hidraw_prefers_interface_3(tmp_path):
    sysfs, dev = tmp_path / "sys", tmp_path / "dev"
    dev.mkdir()
    _make_hid(sysfs, "0003:046D:C332.000E", "0003:0000046D:0000C332", "usb-1/input0", "hidraw0")
    _make_hid(sysfs, "0003:0ECB:2088.0010", "0003:00000ECB:00002088", "usb-2/input0", "hidraw4")
    _make_hid(sysfs, "0003:0ECB:2088.0011", "0003:00000ECB:00002088", "usb-2/input3", "hidraw5")
    for n in ("hidraw0", "hidraw4", "hidraw5"):
        (dev / n).touch()

    assert tray.find_hidraw_device(str(sysfs), str(dev)) == str(dev / "hidraw5")


def test_find_hidraw_never_returns_unrelated_device(tmp_path):
    sysfs, dev = tmp_path / "sys", tmp_path / "dev"
    dev.mkdir()
    _make_hid(sysfs, "0003:046D:C332.000E", "0003:0000046D:0000C332", "usb-1/input0", "hidraw0")
    (dev / "hidraw0").touch()

    assert tray.find_hidraw_device(str(sysfs), str(dev)) is None
    assert tray.find_hidraw_device(str(tmp_path / "missing"), str(dev)) is None


def test_hidraw_reader_drains_fifo(tmp_path):
    r, w = os.pipe()
    os.write(w, bytes([0x08, 0x1E]))
    reader = tray.HidrawBatteryReader("/unused")
    os.set_blocking(r, False)
    reader._fd = r
    battery, mute = reader.poll_all()
    reader.close()
    os.close(w)
    assert battery is not None and battery.percent == 30
    assert mute is None


def test_battery_cache_roundtrip(tmp_path):
    path = str(tmp_path / "sub" / "last_battery.json")
    assert tray.load_cached_battery(path) is None
    tray.save_cached_battery(tray.BatterySample(percent=42, source="pyusb", raw_hex="08 2a", ts=123.0), path)
    cached = tray.load_cached_battery(path)
    assert cached is not None
    assert (cached.percent, cached.source, cached.ts) == (42, tray.CACHE_SOURCE, 123.0)


def test_battery_cache_rejects_invalid(tmp_path):
    path = tmp_path / "last_battery.json"
    path.write_text('{"percent": 250, "ts": 1}')
    assert tray.load_cached_battery(str(path)) is None
    path.write_text("not json")
    assert tray.load_cached_battery(str(path)) is None


def test_format_age():
    assert tray._format_age(5) == "5s"
    assert tray._format_age(600) == "10min"
    assert tray._format_age(5400) == "1.5h"


def test_number_icon_svg():
    svg = tray.render_number_icon_svg(85)
    assert ">85</text>" in svg and tray.number_icon_color(85) in svg
    assert "textLength" in tray.render_number_icon_svg(100)
    assert "<line" in tray.render_number_icon_svg(85, is_muted=True)
    assert tray.number_icon_color(85) not in tray.render_number_icon_svg(85, stale=True)
    assert tray.number_icon_color(20) != tray.number_icon_color(5)


def test_ensure_number_icon_writes_file(tmp_path):
    name = tray.ensure_number_icon(42, True, str(tmp_path))
    assert name == "jbl-quantum910-v2-42-muted"
    assert tray.ensure_number_icon(42, False, str(tmp_path), stale=True) == "jbl-quantum910-v2-42-stale"
    assert any(p.name.startswith(name) for p in tmp_path.iterdir())
