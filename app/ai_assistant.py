"""The AI assistant.

Two engines live behind one function, `diagnose()`:

  "claude"     - calls the Anthropic API with a structured prompt and parses
                 a strict JSON reply. Used when ANTHROPIC_API_KEY is set.
  "heuristic"  - a local keyword-and-evidence engine with no external calls.
                 Used when there is no API key, so the pipeline, the web app
                 and the demo all still work offline.

Every diagnosis records which engine produced it. They are never mixed or
presented as the same thing.

Nothing in this module applies a fix or writes to a device. It only proposes.
A human decision is required before anything is treated as correct.
"""
from typing import List, Literal

import anthropic
from pydantic import BaseModel, Field

from app.config import AI_MODEL, ANTHROPIC_API_KEY

SYSTEM_PROMPT = """You are a network troubleshooting assistant for a Cisco \
Packet Tracer lab. You help junior engineers move from a symptom to a likely \
root cause.

Rules you must follow:
- Base the diagnosis only on the evidence supplied. Do not invent command \
output that was not given to you.
- If the evidence is thin, say so by lowering your confidence. A confident \
wrong answer is worse than an honest uncertain one.
- Always name the single most likely root cause, not a list of maybes.
- Always give one concrete next command that would confirm or rule out your \
diagnosis.
- The deterministic findings supplied to you are facts. Reason with them, not \
around them."""


class ProposedDiagnosis(BaseModel):
    """The exact shape every proposal must take.

    This is passed to the API as a schema, so the model cannot reply with
    prose, a code fence, a missing field or a fault type we do not recognise.
    The old version asked for JSON in the prompt and parsed whatever came
    back; this cannot fail in that way.
    """

    root_cause: str = Field(
        description="One sentence naming the single most likely misconfiguration."
    )
    fault_type: Literal[
        "VLAN", "DHCP", "DNS", "ROUTING", "ACL", "NAT", "PHYSICAL", "OTHER"
    ] = Field(description="The category this fault belongs to.")
    osi_layer: Literal[
        "Layer 1", "Layer 2", "Layer 3", "Layer 4", "Layer 7"
    ] = Field(description="Which layer the fault sits at.")
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="0 to 1. Lower it honestly when the evidence is thin.",
    )
    evidence: str = Field(
        description="The specific lines of supplied output that support this."
    )
    next_command: str = Field(
        description="One command that would confirm or rule out this diagnosis."
    )
    fix_steps: List[str] = Field(
        description="Two to four short imperative steps that resolve it."
    )

USER_TEMPLATE = """Symptom reported by the user:
{symptom}

Topology notes:
{topology}

Command output collected so far:
{show_output}

Deterministic checks already run against this case (these are facts, not \
guesses - take them into account):
{rule_summary}

Diagnose this case."""


# ---------------------------------------------------------------------------
# Claude engine
# ---------------------------------------------------------------------------

_client = None


def _get_client():
    """One Anthropic client, created on first use.

    Building it lazily means importing this module never needs a key, so the
    CLI, the tests and the offline demo all still work without one.
    """
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=60.0)
    return _client


def _call_claude(symptom, topology, show_output, rule_summary):
    """Ask Claude for one proposal, guaranteed to arrive in the right shape."""
    response = _get_client().messages.parse(
        model=AI_MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": USER_TEMPLATE.format(
                symptom=symptom or "(none given)",
                topology=topology or "(none given)",
                show_output=show_output or "(none given)",
                rule_summary=rule_summary or "(no deterministic findings)",
            ),
        }],
        output_format=ProposedDiagnosis,
    )
    return response.parsed_output


# ---------------------------------------------------------------------------
# Heuristic engine (offline fallback)
# ---------------------------------------------------------------------------

# Ordered most-specific first. The first pattern that matches wins.
_SIGNATURES = [
    {
        "keys": ("169.254", "apipa", "no dhcp", "dhcp server", "did not obtain",
                 "limited connectivity"),
        "root_cause": "The DHCP server or relay is not reachable from this VLAN, "
                      "so the host fell back to a self-assigned address.",
        "fault_type": "DHCP", "osi_layer": "Layer 3", "confidence": 0.72,
        "next_command": "show ip dhcp pool",
        "fix_steps": "Confirm the DHCP pool has free addresses and that an "
                     "ip helper-address points at the DHCP server from this VLAN.",
    },
    {
        "keys": ("nxdomain", "non-existent domain", "unknown host",
                 "dns request timed out", "can't find", "resolves"),
        "root_cause": "DNS resolution is failing while IP connectivity is intact; "
                      "the configured DNS server is wrong or unreachable.",
        "fault_type": "DNS", "osi_layer": "Layer 7", "confidence": 0.75,
        "next_command": "nslookup <hostname> <dns-server-ip>",
        "fix_steps": "Correct the DNS server address handed out by DHCP, and "
                     "confirm the DNS server itself is reachable and answering.",
    },
    {
        "keys": ("access-list", "acl", "deny", "permit ip", "blocked by"),
        "root_cause": "An access control list is denying the traffic between "
                      "these two subnets.",
        "fault_type": "ACL", "osi_layer": "Layer 4", "confidence": 0.68,
        "next_command": "show access-lists",
        "fix_steps": "Add a permit entry for the required source/destination pair "
                     "above the denying line, then re-apply the ACL.",
    },
    {
        "keys": ("nat translation", "ip nat", "inside global", "outside local"),
        "root_cause": "The NAT translation for this host is missing or maps to "
                      "the wrong inside address.",
        "fault_type": "NAT", "osi_layer": "Layer 3", "confidence": 0.66,
        "next_command": "show ip nat translations",
        "fix_steps": "Add or correct the static NAT entry, and confirm ip nat "
                     "inside / outside are set on the right interfaces.",
    },
    {
        "keys": ("trunk", "vlan", "switchport", "native vlan"),
        "root_cause": "The switch port is in the wrong VLAN, or the trunk is not "
                      "carrying the VLAN this host needs.",
        "fault_type": "VLAN", "osi_layer": "Layer 2", "confidence": 0.7,
        "next_command": "show vlan brief",
        "fix_steps": "Set the access port to the correct VLAN, and add that VLAN "
                     "to the allowed list on the uplink trunk.",
    },
    {
        "keys": ("gateway of last resort", "show ip route", "no route",
                 "destination host unreachable", "network unreachable"),
        "root_cause": "There is no route from this subnet to the destination "
                      "network in the routing table.",
        "fault_type": "ROUTING", "osi_layer": "Layer 3", "confidence": 0.7,
        "next_command": "show ip route",
        "fix_steps": "Add the missing static route, or confirm the routing "
                     "protocol is advertising the destination network.",
    },
    {
        "keys": ("administratively down", "down down", "line protocol is down",
                 "cable", "link light"),
        "root_cause": "The interface carrying this traffic is down.",
        "fault_type": "PHYSICAL", "osi_layer": "Layer 1", "confidence": 0.8,
        "next_command": "show ip interface brief",
        "fix_steps": "Issue no shutdown on the interface, and confirm the cable "
                     "type and port are correct.",
    },
]

_FALLBACK = {
    "root_cause": "Evidence is insufficient to name a single root cause; the "
                  "fault is somewhere past the default gateway.",
    "fault_type": "OTHER", "osi_layer": "Layer 3", "confidence": 0.3,
    "next_command": "show ip route",
    "fix_steps": "Collect show ip route, show vlan brief and show access-lists, "
                 "then re-run the diagnosis with that output attached.",
}


def _heuristic(symptom, topology, show_output, rule_findings):
    blob = f"{symptom}\n{topology}\n{show_output}".lower()

    # A deterministic finding outranks keyword matching: it is a known fact.
    rule_map = {
        "DUPLICATE_IP": ("An IP address conflict is preventing this host from "
                         "communicating reliably.", "OTHER", "Layer 3", 0.9,
                         "show ip interface brief"),
        "APIPA_ADDRESS": ("No DHCP server answered, so the host self-assigned "
                          "a 169.254 address.", "DHCP", "Layer 3", 0.9,
                          "show ip dhcp pool"),
        "GATEWAY_OFF_SUBNET": ("The default gateway is not inside the host's own "
                               "subnet, so nothing can leave the subnet.",
                               "ROUTING", "Layer 3", 0.9, "show run interface"),
        "INVALID_SUBNET_MASK": ("The subnet mask is not a valid contiguous mask.",
                                "OTHER", "Layer 3", 0.88, "show run interface"),
        "INTERFACE_DOWN": ("An interface on the path is down.", "PHYSICAL",
                           "Layer 1", 0.88, "show ip interface brief"),
        "DNS_RESOLUTION_FAILURE": ("Name resolution fails while IP connectivity "
                                   "works, so DNS is at fault.", "DNS",
                                   "Layer 7", 0.85, "nslookup <hostname>"),
        "VLAN_SUBNET_MISMATCH": ("A port appears to be in the wrong VLAN.",
                                 "VLAN", "Layer 2", 0.8, "show vlan brief"),
        "NO_DEFAULT_ROUTE": ("No gateway of last resort is configured.",
                             "ROUTING", "Layer 3", 0.82, "show ip route"),
    }
    for finding in rule_findings or []:
        hit = rule_map.get(finding.get("rule_code"))
        if hit:
            cause, ftype, layer, conf, cmd = hit
            return {
                "root_cause": cause,
                "fault_type": ftype,
                "osi_layer": layer,
                "confidence": conf,
                "evidence": finding.get("evidence") or finding.get("message", ""),
                "next_command": cmd,
                "fix_steps": "Correct the item named above, then re-test "
                             "connectivity end to end.",
            }

    for sig in _SIGNATURES:
        if any(k in blob for k in sig["keys"]):
            out = dict(sig)
            out.pop("keys")
            out["evidence"] = "Matched on terms present in the supplied output."
            return out

    out = dict(_FALLBACK)
    out["evidence"] = "No distinguishing signature found in the supplied output."
    return out


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def _normalise(raw, engine):
    """Coerce whatever came back into the shape the database expects."""
    def _s(key, default=""):
        val = raw.get(key, default)
        if isinstance(val, str):
            return val.strip()
        if isinstance(val, (list, tuple)):
            # Models often return fix_steps / evidence as a list. Store one
            # item per line so the UI can split it back into steps.
            return "\n".join(str(v).strip() for v in val if str(v).strip())
        return str(val)

    try:
        confidence = float(raw.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    return {
        "root_cause": _s("root_cause") or "No root cause returned.",
        "fault_type": (_s("fault_type") or "OTHER").upper()[:32],
        "osi_layer": _s("osi_layer")[:16],
        "confidence": confidence,
        "evidence": _s("evidence"),
        "next_command": _s("next_command"),
        "fix_steps": _s("fix_steps"),
        "engine": engine,
    }


def diagnose(symptom, topology_notes="", show_output="", rule_findings=None):
    """Produce one proposed diagnosis. Returns a dict ready for the DB.

    Falls back to the heuristic engine if the API key is absent or the call
    fails, so the pipeline never stalls. The `engine` field always records
    which path was actually taken.
    """
    rule_summary = "\n".join(
        f"- [{f.get('severity', '?')}] {f.get('rule_code')}: {f.get('message')}"
        for f in (rule_findings or [])
    )

    if ANTHROPIC_API_KEY:
        try:
            proposal = _call_claude(
                symptom, topology_notes, show_output, rule_summary
            )
            result = _normalise(proposal.model_dump(), "claude")
            result["raw_response"] = proposal.model_dump_json()
            return result
        except anthropic.APIError as exc:
            # Any API failure - bad key, rate limit, timeout, server error -
            # falls back to the local engine so the pipeline never stalls. The
            # engine field records which one actually ran.
            fallback = _normalise(
                _heuristic(symptom, topology_notes, show_output, rule_findings),
                "heuristic",
            )
            fallback["raw_response"] = f"Claude call failed, used heuristic: {exc}"
            return fallback

    result = _normalise(
        _heuristic(symptom, topology_notes, show_output, rule_findings),
        "heuristic",
    )
    result["raw_response"] = "No API key configured; heuristic engine used."
    return result


# ---------------------------------------------------------------------------
# Free-text chat (used by the console's case-grounded assistant)
# ---------------------------------------------------------------------------

CHAT_UNAVAILABLE = (
    "No AI engine is reachable from this server right now, so I cannot answer "
    "follow-ups. The proposal above came from the local heuristic engine - "
    "check its evidence against the device yourself before acting."
)


def chat(system, messages, max_tokens=1000):
    """Answer a follow-up question about an open case.

    Returns (reply_text, engine). There is no offline model for free-text
    conversation, so without an API key this says so plainly rather than
    inventing an answer.
    """
    if not ANTHROPIC_API_KEY:
        return CHAT_UNAVAILABLE, "unavailable"

    turns = [
        {"role": m.get("role", "user"), "content": m.get("content", "")}
        for m in messages
        if (m.get("content") or "").strip()
    ]
    if not turns:
        return CHAT_UNAVAILABLE, "unavailable"

    try:
        response = _get_client().messages.create(
            model=AI_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=turns,
        )
    except anthropic.APIError:
        return CHAT_UNAVAILABLE, "unavailable"

    text = "".join(
        block.text for block in response.content if block.type == "text"
    ).strip()
    return (text or CHAT_UNAVAILABLE), ("claude" if text else "unavailable")
