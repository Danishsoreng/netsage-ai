"""End-to-end smoke test: every route the console UI depends on."""
import json
import os
import sys

sys.path.insert(0, os.path.abspath("."))

from app.db import init_db
from app.web import app
from run import seed_if_empty

init_db()
seed_if_empty()

c = app.test_client()
fails = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + (("  <- " + str(detail)) if not cond else ""))
    if not cond:
        fails.append(name)


# --- pages -----------------------------------------------------------------
for path, needle in [
    ("/", "x-dc"),
    ("/overview", "x-dc"),
    ("/support.js", "dc-runtime"),
    ("/queue", "NetSage"),
    ("/dashboard", "NetSage"),
]:
    r = c.get(path)
    body = r.get_data(as_text=True)
    check("GET %-12s -> 200" % path, r.status_code == 200, r.status_code)
    check("GET %-12s contains %s" % (path, needle), needle in body, body[:120])

# --- health ----------------------------------------------------------------
r = c.get("/api/health")
h = r.get_json()
check("GET /api/health", r.status_code == 200 and h.get("ok"), h)
print("        engine=%s db=%s cases=%s" % (h.get("engine"), h.get("database"), h.get("cases")))

# --- triage: the full stage 2 + 3 chain ------------------------------------
SHOW = """PC-204   192.168.30.15   255.255.255.0   192.168.40.1   vlan30
PC-205   192.168.30.16   255.255.255.0   192.168.30.1   vlan30
FastEthernet0/3 is administratively down, line protocol is down
"""
r = c.post("/api/triage", json={
    "symptom": "PC in room 204 gets an IP but cannot reach the file server",
    "topology": "Access switch SW-204 -> uplink Gi0/1 -> core SW-CORE, VLAN 30",
    "show_output": SHOW,
})
t = r.get_json()
check("POST /api/triage -> 200", r.status_code == 200, t)
check("triage returns a case_ref", bool(t.get("case_ref")), t)
check("triage persisted a diagnosis id", bool(t.get("diagnosis_id")), t)
check("triage ran the rule checker", len(t.get("findings") or []) > 0, t.get("findings"))
check("triage returned a proposal", bool((t.get("dx") or {}).get("root_cause")), t.get("dx"))
check("fix_steps is a list for the UI", isinstance((t.get("dx") or {}).get("fix_steps"), list), t.get("dx"))
print("        case=%s engine=%s findings=%s" % (
    t.get("case_ref"), t.get("engine"), [f["code"] for f in t.get("findings", [])]))
print("        root_cause=%s" % (t.get("dx") or {}).get("root_cause"))

# --- triage rejects an empty case -----------------------------------------
r = c.post("/api/triage", json={"symptom": "", "show_output": ""})
check("POST /api/triage empty -> 400", r.status_code == 400, r.status_code)

# --- review ----------------------------------------------------------------
r = c.post("/api/review", json={
    "diagnosis_id": t["diagnosis_id"], "case_ref": t["case_ref"],
    "decision": "edited", "reviewer": "smoke",
    "corrected_root_cause": "Access port left in VLAN 40 after a patching change.",
    "reviewer_notes": "Confirmed on the switch.",
})
rv = r.get_json()
check("POST /api/review -> 200", r.status_code == 200 and rv.get("ok"), rv)

r = c.post("/api/review", json={"diagnosis_id": t["diagnosis_id"], "decision": "nonsense"})
check("POST /api/review bad decision -> 400", r.status_code == 400, r.status_code)

# --- chat ------------------------------------------------------------------
r = c.post("/api/chat", json={"question": "why that command?", "symptom": "x", "dx": t.get("dx")})
ch = r.get_json()
check("POST /api/chat -> 200", r.status_code == 200 and bool(ch.get("reply")), ch)
print("        chat engine=%s" % ch.get("engine"))

# --- metrics ---------------------------------------------------------------
r = c.get("/api/metrics")
mm = r.get_json()
m = (mm or {}).get("metrics", {})
check("GET /api/metrics -> 200", r.status_code == 200, r.status_code)
check("metrics has the four stat-band numbers",
      all(k in m for k in ("total_cases", "total_rule_findings", "total_diagnoses", "reviewed")), m)
check("metrics queue is populated", len(mm.get("queue") or []) > 0, len(mm.get("queue") or []))
check("the edit shows up in the correction log",
      any(x["case_ref"] == t["case_ref"] for x in mm.get("corrections") or []),
      mm.get("corrections"))
print("        cases=%s findings=%s diagnoses=%s reviewed=%s queue=%s corrections=%s" % (
    m.get("total_cases"), m.get("total_rule_findings"), m.get("total_diagnoses"),
    m.get("reviewed"), len(mm.get("queue") or []), len(mm.get("corrections") or [])))

# --- the server-rendered case page still works -----------------------------
r = c.get("/case/" + t["case_ref"])
check("GET /case/<ref> -> 200", r.status_code == 200, r.status_code)

print("")
print("FAILED: %s" % fails if fails else "all checks passed")
sys.exit(1 if fails else 0)
