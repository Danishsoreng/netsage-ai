"""Flask front end for NetSage AI.

Two front ends share one backend.

The console (the `netsage-ui/*.dc.html` design files) is the primary screen:

    /            triage console - describe a fault, get rule findings and an
                 AI proposal, then accept / edit / reject it
    /overview    the rolled-up pipeline overview, fed live from the database

The original server-rendered screens are still here and read the same tables:

    /queue       the queue of ingested cases and their review state
    /case/<ref>  one case: evidence, rule findings, AI proposal, review form
    /dashboard   rolled-up numbers

Both front ends talk to the same code. The console goes through `app.api`;
the server-rendered pages go through the routes below. Neither has a path that
auto-accepts an AI answer - a diagnosis is only ever marked correct by a human
decision landing in the `reviews` table.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import (
    Flask, redirect, render_template, request, send_from_directory, url_for,
)

from app import pipeline
from app.api import api
from app.config import (
    AI_ENABLED, DATABASE_URL, LOW_CONFIDENCE_THRESHOLD, PROJECT_ROOT,
)
from app.db import init_db, session_scope
from app.models import Case, DECISIONS, Diagnosis, Review, RuleFinding

app = Flask(__name__)
app.register_blueprint(api)

# The console UI ships as two self-contained design files plus the runtime
# they load. They are served from disk rather than copied into templates/,
# so the design files stay the single source of truth for the interface.
UI_DIR = os.path.join(PROJECT_ROOT, "netsage-ui")
TRIAGE_PAGE = "NetSage Triage.dc.html"
OVERVIEW_PAGE = "NetSage Console.dc.html"

LAYER_ORDER = ["Layer 1", "Layer 2", "Layer 3", "Layer 4", "Layer 7"]


def _layer_slug(layer):
    digits = "".join(c for c in (layer or "") if c.isdigit())
    return f"l{digits}" if digits else "lx"


app.jinja_env.filters["layer_slug"] = _layer_slug


@app.route("/")
def console():
    """The triage console. Its JS calls the /api routes registered above."""
    return send_from_directory(UI_DIR, TRIAGE_PAGE)


@app.route("/overview")
def overview():
    """The pipeline overview, populated from GET /api/metrics on load."""
    return send_from_directory(UI_DIR, OVERVIEW_PAGE)


@app.route("/support.js")
def ui_runtime():
    """The runtime both design files load with a relative <script src>."""
    return send_from_directory(UI_DIR, "support.js")


@app.route("/queue")
def index():
    with session_scope() as s:
        cases = s.query(Case).order_by(Case.case_ref).all()
        rows = []
        for c in cases:
            diag = c.latest_diagnosis
            review = diag.review if diag else None
            rows.append({
                "case": c,
                "diagnosis": diag,
                "review": review,
                "state": review.decision if review else "pending",
                "low_confidence": bool(
                    diag and diag.confidence < LOW_CONFIDENCE_THRESHOLD
                ),
            })
    counts = {
        "pending": sum(1 for r in rows if r["state"] == "pending"),
        "accepted": sum(1 for r in rows if r["state"] == "accepted"),
        "edited": sum(1 for r in rows if r["state"] == "edited"),
        "rejected": sum(1 for r in rows if r["state"] == "rejected"),
    }
    return render_template(
        "index.html", rows=rows, counts=counts, ai_enabled=AI_ENABLED
    )


@app.route("/case/<case_ref>")
def case_detail(case_ref):
    with session_scope() as s:
        case = s.query(Case).filter_by(case_ref=case_ref).one_or_none()
        if case is None:
            return render_template("not_found.html", case_ref=case_ref), 404
        findings = s.query(RuleFinding).filter_by(case_id=case.id).all()
        diag = case.latest_diagnosis
        review = diag.review if diag else None
    return render_template(
        "case_detail.html",
        case=case, findings=findings, diagnosis=diag, review=review,
        decisions=DECISIONS, layer_order=LAYER_ORDER,
        low_threshold=LOW_CONFIDENCE_THRESHOLD,
    )


@app.route("/case/<case_ref>/review", methods=["POST"])
def submit_review(case_ref):
    decision = request.form.get("decision", "").strip().lower()
    if decision not in DECISIONS:
        return redirect(url_for("case_detail", case_ref=case_ref))

    with session_scope() as s:
        case = s.query(Case).filter_by(case_ref=case_ref).one_or_none()
        if case is None:
            return redirect(url_for("index"))
        diag = case.latest_diagnosis
        if diag is None:
            return redirect(url_for("case_detail", case_ref=case_ref))

        review = s.query(Review).filter_by(diagnosis_id=diag.id).one_or_none()
        if review is None:
            review = Review(diagnosis_id=diag.id)
            s.add(review)

        review.decision = decision
        review.reviewer = request.form.get("reviewer", "").strip()[:64]
        review.corrected_root_cause = request.form.get(
            "corrected_root_cause", ""
        ).strip()
        review.reviewer_notes = request.form.get("reviewer_notes", "").strip()

    return redirect(url_for("case_detail", case_ref=case_ref))


@app.route("/dashboard")
def dashboard():
    metrics = pipeline.build_metrics()
    with session_scope() as s:
        corrections = (
            s.query(Review)
            .filter(Review.decision.in_(("edited", "rejected")))
            .order_by(Review.created_at.desc())
            .all()
        )
        correction_rows = []
        for r in corrections:
            d = s.get(Diagnosis, r.diagnosis_id)
            c = s.get(Case, d.case_id) if d else None
            correction_rows.append({"review": r, "diagnosis": d, "case": c})
    return render_template(
        "dashboard.html", m=metrics, corrections=correction_rows,
        ai_enabled=AI_ENABLED, db_url=DATABASE_URL.split("://")[0],
    )


if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=5000, debug=True)
