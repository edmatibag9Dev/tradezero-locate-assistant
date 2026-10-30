"""Tests for who may use the console (src/access.py). Run: python3 tests/test_access.py"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import access  # noqa: E402

NETS = access.parse_networks(None)
passed = failed = 0


def check(name, got, want):
    global passed, failed
    ok = got == want
    passed += ok
    failed += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {name}: got {got!r}" + ("" if ok else f", want {want!r}"))


for ip, want, why in [
    ("127.0.0.1", True, "this Mac"),
    ("::1", True, "this Mac (IPv6)"),
    ("192.168.0.134", True, "home network"),
    ("10.0.0.5", True, "private 10/8"),
    ("172.20.1.9", True, "private 172.16/12"),
    ("100.101.102.103", True, "Tailscale IPv4"),
    ("fd7a:115c:a1e0::1234", True, "Tailscale IPv6"),
    ("::ffff:192.168.0.10", True, "IPv4-mapped home address"),
    ("8.8.8.8", False, "public internet"),
    ("172.32.0.1", False, "just outside 172.16/12"),
    ("100.128.0.1", False, "just outside Tailscale range"),
    ("2001:4860::8888", False, "public IPv6"),
    ("::ffff:8.8.8.8", False, "IPv4-mapped public"),
    ("not-an-ip", False, "garbage"),
]:
    check(f"{why} {ip}", access.client_allowed(ip, NETS), want)

custom = access.parse_networks(["127.0.0.1/32", "192.168.0.0/24"])
check("custom list: other home subnet refused", access.client_allowed("192.168.1.5", custom), False)
check("custom list: listed subnet allowed", access.client_allowed("192.168.0.5", custom), True)
check("funnel header refused", access.relayed_from_public({"Tailscale-Funnel-Request": "?1"}), True)
check("normal request not flagged", access.relayed_from_public({"Host": "eds-mac-studio:8765"}), False)

print(f"\n{passed}/{passed + failed} passed")
sys.exit(1 if failed else 0)
