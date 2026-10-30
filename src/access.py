"""Who may use the console: this Mac, the home network, and Tailscale devices.

The console can accept locates (real money), so with --lan it must not answer
anyone else. Checked on every request, independent of the macOS firewall.
Stdlib only; pure functions so tests/test_access.py can cover them.

Defaults (override with "allowed_networks" in config.json):
  127.0.0.0/8, ::1/128           this Mac
  10/8, 172.16/12, 192.168/16    private home-network ranges (RFC 1918)
  100.64.0.0/10                  Tailscale device addresses (IPv4)
  fd7a:115c:a1e0::/48            Tailscale device addresses (IPv6)

Requests relayed by Tailscale Funnel (public internet → tailscaled → this Mac)
arrive from 127.0.0.1, so the source address alone can't catch them; they carry
a Tailscale-Funnel-Request header and are refused.
"""

from __future__ import annotations

import ipaddress

DEFAULT_ALLOWED = [
    "127.0.0.0/8", "::1/128",
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
    "100.64.0.0/10", "fd7a:115c:a1e0::/48",
]

# Headers that mean the request was relayed from outside the tailnet.
PUBLIC_RELAY_HEADERS = ("Tailscale-Funnel-Request",)


def parse_networks(cidrs: list[str] | None) -> list:
    nets = []
    for c in (cidrs or DEFAULT_ALLOWED):
        nets.append(ipaddress.ip_network(str(c).strip(), strict=False))
    return nets


def client_allowed(ip: str, nets: list) -> bool:
    """True if the source address is inside one of the allowed networks."""
    try:
        addr = ipaddress.ip_address(ip.split("%")[0])
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped  # ::ffff:192.168.0.10 → 192.168.0.10
    return any(addr.version == n.version and addr in n for n in nets)


def relayed_from_public(headers) -> bool:
    """True if a header shows the request came in through a public relay."""
    return any(headers.get(h) is not None for h in PUBLIC_RELAY_HEADERS)
