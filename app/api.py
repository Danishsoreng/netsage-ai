"""JSON API behind the NetSage console UI.

The design files in `netsage-ui/` used to run the rule checker in the browser
and call an in-page model. Both are now server side: every route here goes
through the same `rule_checker`, `ai_assistant` and database code that the
Airflow pipeline and the CLI use, so a case triaged from the console becomes a
real row in `cases`, `rule_findings`, `diagnoses` and `reviews`.

Routes:
    POST /api/triage   symptom + output -> rule findings + AI proposal (saved)
    POST /api/review   a human decision on one proposal (saved)
    POST /api/chat     a follow-up question grounded in one case
    GET  /api/metrics  dashboard numbers, review queue, correction log
    GET  /api/health   engine + database status
"""
import re

from flask import Blueprint, jsonify, request

from app import ai_assistant, pipeline, rule_checker
from app.config import (
    AI_ENABLED, AI_MODEL, DATABASE_URL, LOW_CONFIDENCE_THRESHOLD,
)
from app.db import session_scope
from app.models import Case, DECISIONS, Diagnosis, Review, RuleFinding

api = Blueprint("api", __name__, url_prefix="/api")

SEVERITY_COLOR = {
    "high": "oklch(0.7 0.16 25)",
    "medium": "oklch(0.82 0.14 85)",
    "low": "oklch(0.72 0.13 200)",
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _body():
    return request.get_json(silent=True) or {}


def _next_case_ref(session):
    """Allocate the next LIVE-#### reference for a console-entered case."""
    refs = [
        r[0] for r in session.query(Case.case_ref)
        .filter(Case.case_ref.like("LIVE-%")).all()
    ]
    highest = 0
    for ref in refs:
        m = re.match(r"^LIVE-(\d+)$", ref or "")
        if m:
            highest = max(highest, int(m.group(1)))
    return "LIVE-%04d" % (highest + 1)


def _finding_payload(rule_code, severity, message, evidence):
    return {
        "code": rule_code,
        "rule_code": rule_code,
        "severity": severity,
        "message": message,
        "evidence": evidence,
        "color": SEVERITY_COLOR.get(severity, SEVERITY_COLOR["low"]),
    }


def _split_steps(fix_steps):
    """`fix_steps` is stored as text; the console renders it as a step list."""
    if not fix_steps:
        return []
    parts = [p.strip(" -*•") for p in str(fix_steps).splitlines() if p.strip()]
    if len(parts) == 1:
        # One long sentence: break it on sentence boundaries instead.
        parts = [s.strip() for s in re.split(r"(?<=[.!?])\s+", parts[0]) if s.strip()]
    return parts


def _short_layer(layer):
    """"Layer 3" -> "L3", so the console's compact badge stays compact."""
    digits = "".join(c for c in (layer or "") if c.isdigit())
    return "L" + digits if digits else (layer or "-")


def _diagnosis_payload(diag):
    return {
        "root_cause": diag.root_cause,
        "fault_type": (diag.fault_type or "unknown").lower(),
        "osi_layer": _short_layer(diag.osi_layer),
        "confidence": diag.confidence,
        "evidence": diag.evidence,
        "next_command": diag.next_command,
        "fix_steps": _split_steps(diag.fix_steps),
        "engine": diag.engine,
        "low_confidence": (diag.confidence or 0.0) < LOW_CONFIDENCE_THRESHOLD,
    }


# ---------------------------------------------------------------------------
# POST /api/triage
# ---------------------------------------------------------------------------

@api.post("/triage")
def triage():
    """Stages 2 and 3 for one case typed into the console.

    Runs the deterministic checker first and passes its findings to the AI as
    established facts, exactly as the batch pipeline does. Nothing here marks a
    proposal as correct; that still needs POST /api/review.
    """
    data = _body()
    symptom = (data.get("symptom") or "").strip()
    topology = (data.get("topology") or data.get("topology_notes") or "").strip()
    show_output = (data.get("show_output") or data.get("showOutput") or "").strip()

    if not symptom and not show_output:
        return jsonify({"error": "Give a symptom or some command output."}), 400

    findings = rule_checker.check(show_output, topology)

    result = ai_assistant.diagnose(
        symptom=symptom,
        topology_notes=topology,
        show_output=show_output,
        rule_findings=findings,
    )

    with session_scope() as s:
        case_ref = (data.get("case_ref") or "").strip() or _next_case_ref(s)
        case = s.query(Case).filter_by(case_ref=case_ref).one_or_none()
        if case is None:
            case = Case(case_ref=case_ref)
            s.add(case)
        case.symptom = symptom
        case.topology_notes = topology
        case.show_output = show_output
        s.flush()

        s.query(RuleFinding).filter_by(case_id=case.id).delete()
        for f in findings:
            s.add(RuleFinding(
                case_id=case.id,
                rule_code=f["rule_code"],
                severity=f["severity"],
                message=f["message"],
                evidence=f["evidence"],
            ))

        diag = Diagnosis(case_id=case.id, **result)
        s.add(diag)
        s.flush()
        payload = {
            "case_ref": case_ref,
            "diagnosis_id": diag.id,
            "engine": diag.engine,
            "findings": [
                _finding_payload(
                    f["rule_code"], f["severity"], f["message"], f["evidence"]
                )
                for f in findings
            ],
            "dx": _diagnosis_payload(diag),
        }

    return jsonify(payload)


# ---------------------------------------------------------------------------
# POST /api/review
# ---------------------------------------------------------------------------

@api.post("/review")
def review():
    """Record the human decision. This is the only route that closes a case."""
    data = _body()
    decision = (data.get("decision") or "").strip().lower()
    if decision not in DECISIONS:
        return jsonify({"error": "decision must be one of " + ", ".join(DECISIONS)}), 400

    with session_scope() as s:
        diag = None
        if data.get("diagnosis_id"):
            diag = s.get(Diagnosis, int(data["diagnosis_id"]))
        elif data.get("case_ref"):
            case = s.query(Case).filter_by(
                case_ref=str(data["case_ref"]).strip()
            ).one_or_none()
            diag = case.latest_diagnosis if case else None
        if diag is None:
            return jsonify({"error": "No diagnosis found for that case."}), 404

        row = s.query(Review).filter_by(diagnosis_id=diag.id).one_or_none()
        if row is None:
            row = Review(diagnosis_id=diag.id)
            s.add(row)
        row.decision = decision
        row.reviewer = (data.get("reviewer") or "").strip()[:64]
        row.corrected_root_cause = (
            data.get("corrected_root_cause") or data.get("corrected") or ""
        ).strip()
        row.reviewer_notes = (
            data.get("reviewer_notes") or data.get("notes") or ""
        ).strip()
        s.flush()
        out = {
            "ok": True,
            "review_id": row.id,
            "diagnosis_id": diag.id,
            "decision": row.decision,
        }
    return jsonify(out)


# ---------------------------------------------------------------------------
# POST /api/chat
# ---------------------------------------------------------------------------

@api.post("/chat")
def chat():
    """A follow-up question, grounded in one case. Read-only: changes nothing."""
    data = _body()
    question = (data.get("question") or "").strip()
    if not question:
        return jsonify({"error": "empty question"}), 400

    findings = data.get("findings") or []
    codes = ", ".join(
        f.get("code") or f.get("rule_code") or "" for f in findings
    ).strip(", ") or "none"
    dx = data.get("dx") or {}
    if dx.get("root_cause"):
        proposal = "%s (%s, confidence %s)" % (
            dx.get("root_cause"), dx.get("osi_layer"), dx.get("confidence"),
        )
    else:
        proposal = "none yet"

    system = (
        "You are NetSage AI's assistant, talking to a junior network engineer "
        "about one open case. Answer in at most 90 words, plain and concrete, "
        "no bullet lists unless listing commands. Never claim to have touched "
        "a device.\n\n"
        "Case symptom: " + (data.get("symptom") or "(none)") + "\n"
        "Rule findings: " + codes + "\n"
        "Current proposal: " + proposal
    )

    history = [
        {"role": m.get("role", "user"),
         "content": m.get("content") or m.get("text") or ""}
        for m in (data.get("history") or [])
    ]
    history.append({"role": "user", "content": question})

    reply, engine = ai_assistant.chat(system, history)
    return jsonify({"reply": reply, "engine": engine})


# ---------------------------------------------------------------------------
# GET /api/metrics
# ---------------------------------------------------------------------------

@api.get("/metrics")
def metrics():
    """Everything the overview screen shows, straight from the four tables."""
    m = pipeline.build_metrics()

    with session_scope() as s:
        queue, corrections = [], []
        for case in s.query(Case).order_by(Case.case_ref).all():
            diag = case.latest_diagnosis
            if diag is None:
                continue
            rev = s.query(Review).filter_by(diagnosis_id=diag.id).one_or_none()
            queue.append({
                "case_ref": case.case_ref,
                "symptom": case.symptom,
                "root_cause": diag.root_cause,
                "fault_type": (diag.fault_type or "").upper(),
                "osi_layer": _short_layer(diag.osi_layer),
                "confidence": round(diag.confidence or 0.0, 2),
                "evidence": diag.evidence,
                "next_command": diag.next_command,
                "diagnosis_id": diag.id,
                "engine": diag.engine,
                "state": rev.decision if rev else "pending",
                "low_confidence": (diag.confidence or 0.0)
                < LOW_CONFIDENCE_THRESHOLD,
            })

        rows = (
            s.query(Review)
            .filter(Review.decision.in_(("edited", "rejected")))
            .order_by(Review.created_at.desc())
            .limit(12).all()
        )
        for r in rows:
            d = s.get(Diagnosis, r.diagnosis_id)
            c = s.get(Case, d.case_id) if d else None
            corrections.append({
                "case_ref": c.case_ref if c else "-",
                "decision": r.decision,
                "reviewer": r.reviewer,
                "proposed": d.root_cause if d else "",
                "corrected": r.corrected_root_cause,
                "notes": r.reviewer_notes,
                "at": r.created_at.isoformat() if r.created_at else None,
            })

    return jsonify({
        "metrics": m,
        "queue": queue,
        "corrections": corrections,
        "ai_enabled": AI_ENABLED,
        "engine": "claude" if AI_ENABLED else "heuristic",
    })


# ---------------------------------------------------------------------------
# GET /api/health
# ---------------------------------------------------------------------------

@api.get("/health")
def health():
    with session_scope() as s:
        cases = s.query(Case).count()
    return jsonify({
        "ok": True,
        "database": DATABASE_URL.split("://")[0],
        "cases": cases,
        "ai_enabled": AI_ENABLED,
        "model": AI_MODEL if AI_ENABLED else None,
        "engine": "claude" if AI_ENABLED else "heuristic",
    })
