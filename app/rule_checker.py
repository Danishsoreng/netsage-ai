"""Deterministic rule checker.

Plain Python. No AI, no network calls, no randomness. Given the same input
it always returns the same findings.

Why this exists: an AI model produces a *likely* answer. This module produces
*certain* answers for a small set of mechanical mistakes. If the checker says
two hosts share an IP address, that is a fact, not an opinion. Running both
side by side means an obviously wrong AI answer gets contradicted by
something that cannot hallucinate.

Each rule returns zero or more findings shaped as:
    {"rule_code": str, "severity": str, "message": str, "evidence": str}
"""
import ipaddress
import re
from collections import defaultdict

SEV_HIGH, SEV_MEDIUM, SEV_LOW = "high", "medium", "low"

# Matches lines like:  PC1 192.168.10.5 255.255.255.0 192.168.10.1 vlan10
_HOST_LINE = re.compile(
    r"^\s*(?P<name>[\w\-\.]+)\s+"
    r"(?P<ip>\d{1,3}(?:\.\d{1,3}){3})\s+"
    r"(?P<mask>\d{1,3}(?:\.\d{1,3}){3})"
    r"(?:\s+(?P<gw>\d{1,3}(?:\.\d{1,3}){3}))?"
    r"(?:\s+(?P<vlan>vlan\s?\d+))?\s*$",
    re.IGNORECASE,
)


def _parse_hosts(text):
    """Pull host records out of a free-text show/config block."""
    hosts = []
    for line in (text or "").splitlines():
        if line.strip().startswith("#") or not line.strip():
            continue
        m = _HOST_LINE.match(line)
        if not m:
            continue
        d = m.groupdict()
        try:
            ipaddress.IPv4Address(d["ip"])
            ipaddress.IPv4Address(d["mask"])
        except ipaddress.AddressValueError:
            continue
        hosts.append(d)
    return hosts


# ---------------------------------------------------------------------------
# Individual rules
# ---------------------------------------------------------------------------

def rule_duplicate_ip(text, hosts):
    """Two devices configured with the same IPv4 address."""
    seen = defaultdict(list)
    for h in hosts:
        seen[h["ip"]].append(h["name"])
    findings = []
    for ip, names in seen.items():
        if len(names) > 1:
            findings.append({
                "rule_code": "DUPLICATE_IP",
                "severity": SEV_HIGH,
                "message": f"IP address {ip} is assigned to more than one device.",
                "evidence": f"Devices sharing {ip}: {', '.join(sorted(names))}",
            })
    return findings


def rule_invalid_mask(text, hosts):
    """Subnet mask that is not a valid contiguous mask (e.g. 255.255.0.255)."""
    findings = []
    for h in hosts:
        octets = [int(o) for o in h["mask"].split(".")]
        bits = "".join(f"{o:08b}" for o in octets)
        if "01" in bits:  # a zero followed by a one -> not contiguous
            findings.append({
                "rule_code": "INVALID_SUBNET_MASK",
                "severity": SEV_HIGH,
                "message": f"{h['name']} has an invalid subnet mask {h['mask']}.",
                "evidence": f"Mask bit pattern {bits} is not contiguous.",
            })
    return findings


def rule_gateway_off_subnet(text, hosts):
    """Default gateway that does not sit inside the host's own subnet."""
    findings = []
    for h in hosts:
        if not h.get("gw"):
            continue
        try:
            net = ipaddress.IPv4Network(f"{h['ip']}/{h['mask']}", strict=False)
            gw = ipaddress.IPv4Address(h["gw"])
        except (ipaddress.AddressValueError, ipaddress.NetmaskValueError):
            continue
        if gw not in net:
            findings.append({
                "rule_code": "GATEWAY_OFF_SUBNET",
                "severity": SEV_HIGH,
                "message": (
                    f"{h['name']}'s default gateway {h['gw']} is outside its own "
                    f"subnet {net}."
                ),
                "evidence": f"{h['name']} {h['ip']}/{h['mask']} -> gateway {h['gw']}",
            })
    return findings


def rule_apipa_address(text, hosts):
    """169.254.x.x means DHCP never answered."""
    findings = []
    for h in hosts:
        if h["ip"].startswith("169.254."):
            findings.append({
                "rule_code": "APIPA_ADDRESS",
                "severity": SEV_HIGH,
                "message": (
                    f"{h['name']} holds a self-assigned address {h['ip']}, which "
                    f"means no DHCP server replied."
                ),
                "evidence": f"{h['name']} {h['ip']}",
            })
    return findings


def rule_interface_down(text, hosts):
    """An interface reported administratively down or down/down."""
    findings = []
    for line in (text or "").splitlines():
        low = line.lower()
        if "administratively down" in low or re.search(r"\bdown\s+down\b", low):
            iface = line.split()[0] if line.split() else "interface"
            findings.append({
                "rule_code": "INTERFACE_DOWN",
                "severity": SEV_HIGH,
                "message": f"Interface {iface} is down.",
                "evidence": line.strip(),
            })
    return findings


def rule_missing_default_route(text, hosts):
    """A routing table with no gateway of last resort."""
    low = (text or "").lower()
    if "show ip route" not in low and "gateway of last resort" not in low:
        return []
    if "gateway of last resort is not set" in low:
        return [{
            "rule_code": "NO_DEFAULT_ROUTE",
            "severity": SEV_MEDIUM,
            "message": "The router has no gateway of last resort configured.",
            "evidence": "show ip route reports: gateway of last resort is not set",
        }]
    return []


def rule_vlan_mismatch(text, hosts):
    """Hosts in the same VLAN sitting on different subnets, or vice versa."""
    findings = []
    by_vlan = defaultdict(set)
    for h in hosts:
        if not h.get("vlan"):
            continue
        try:
            net = ipaddress.IPv4Network(f"{h['ip']}/{h['mask']}", strict=False)
        except (ipaddress.AddressValueError, ipaddress.NetmaskValueError):
            continue
        by_vlan[h["vlan"].lower().replace(" ", "")].add(str(net))
    for vlan, nets in by_vlan.items():
        if len(nets) > 1:
            findings.append({
                "rule_code": "VLAN_SUBNET_MISMATCH",
                "severity": SEV_MEDIUM,
                "message": (
                    f"{vlan} contains devices from more than one subnet, which "
                    f"usually means a port is in the wrong VLAN."
                ),
                "evidence": f"{vlan} subnets seen: {', '.join(sorted(nets))}",
            })
    return findings


def rule_dns_unreachable_hint(text, hosts):
    """Classic DNS signature: name lookup fails but the IP is reachable."""
    low = (text or "").lower()
    name_fail = any(k in low for k in (
        "non-existent domain", "nxdomain", "can't find", "unknown host",
        "dns request timed out",
    ))
    ip_ok = any(k in low for k in ("reply from", "0% loss", "bytes=32 time"))
    if name_fail and ip_ok:
        return [{
            "rule_code": "DNS_RESOLUTION_FAILURE",
            "severity": SEV_MEDIUM,
            "message": (
                "Name resolution fails while direct IP connectivity succeeds. "
                "The fault is DNS, not routing."
            ),
            "evidence": "Lookup failure present alongside a successful IP ping.",
        }]
    return []


ALL_RULES = (
    rule_duplicate_ip,
    rule_invalid_mask,
    rule_gateway_off_subnet,
    rule_apipa_address,
    rule_interface_down,
    rule_missing_default_route,
    rule_vlan_mismatch,
    rule_dns_unreachable_hint,
)


def check(show_output, topology_notes=""):
    """Run every rule over the supplied text and return a list of findings."""
    text = f"{topology_notes or ''}\n{show_output or ''}"
    hosts = _parse_hosts(text)
    findings = []
    for rule in ALL_RULES:
        try:
            findings.extend(rule(text, hosts))
        except Exception as exc:  # a broken rule must not stop the others
            findings.append({
                "rule_code": "RULE_ERROR",
                "severity": SEV_LOW,
                "message": f"Rule {rule.__name__} failed to run.",
                "evidence": str(exc),
            })
    return findings
