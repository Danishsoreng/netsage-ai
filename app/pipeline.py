"""The four pipeline stages, written as plain functions.

Airflow calls these from its DAG. `scripts/run_pipeline.py` calls exactly the
same functions, so the pipeline can be demonstrated on a laptop with no
Airflow installed and behave identically.

    ingest_cases()    read case JSON files into the database
    run_rule_checks() run the deterministic checker over un-checked cases
    run_diagnoses()   ask the AI assistant for a proposal per case
    build_metrics()   roll everything up into dashboard numbers
"""
import glob
import json
import os

from app import ai_assistant, rule_checker
from app.config import CASE_INTAKE_DIR
from app.db import session_scope
from app.models import Case, Diagnosis, Review, RuleFinding


# ---------------------------------------------------------------------------
# Stage 1 - ingest
# ---------------------------------------------------------------------------

def ingest_cases(case_dir=None):
    """Load every *.json case file into the cases table.

    Idempotent: a case_ref that already exists is updated, not duplicated.
    Safe to re-run on every scheduled pipeline execution.
    """
    case_dir = case_dir or CASE_INTAKE_DIR
    paths = sorted(glob.glob(os.path.join(case_dir, "*.json")))

    inserted = updated = 0
    with session_scope() as s:
        for path in paths:
            with open(path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
            records = payload if isinstance(payload, list) else [payload]

            for rec in records:
                ref = rec.get("case_ref")
                if not ref:
                    continue
                case = s.query(Case).filter_by(case_ref=ref).one_or_none()
                if case is None:
                    case = Case(case_ref=ref)
                    s.add(case)
                    inserted += 1
                else:
                    updated += 1

                case.symptom = rec.get("symptom", "")
                case.topology_notes = rec.get("topology_notes", "")
                case.show_output = rec.get("show_output", "")
                case.actual_root_cause = rec.get("actual_root_cause", "")
                case.actual_fault_type = rec.get("actual_fault_type", "")
                case.actual_osi_layer = rec.get("actual_osi_layer", "")
                case.severity = rec.get("severity", "medium")

    return {"files": len(paths), "inserted": inserted, "updated": updated}


# ---------------------------------------------------------------------------
# Stage 2 - deterministic checks
# ---------------------------------------------------------------------------

def run_rule_checks(force=False):
    """Run the rule checker over cases that have no findings yet."""
    written = 0
    with session_scope() as s:
        cases = s.query(Case).all()
        for case in cases:
            existing = s.query(RuleFinding).filter_by(case_id=case.id).count()
            if existing and not force:
                continue
            if force and existing:
                s.query(RuleFinding).filter_by(case_id=case.id).delete()

            for f in rule_checker.check(case.show_output, case.topology_notes):
                s.add(RuleFinding(
                    case_id=case.id,
                    rule_code=f["rule_code"],
                    severity=f["severity"],
                    message=f["message"],
                    evidence=f["evidence"],
                ))
                written += 1
    return {"findings_written": written}


# ---------------------------------------------------------------------------
# Stage 3 - AI diagnosis
# ---------------------------------------------------------------------------

def run_diagnoses(force=False, limit=None):
    """Produce one AI diagnosis per case that does not already have one."""
    produced = 0
    with session_scope() as s:
        cases = s.query(Case).all()
        for case in cases:
            if limit is not None and produced >= limit:
                break
            has_diag = s.query(Diagnosis).filter_by(case_id=case.id).count()
            if has_diag and not force:
                continue

            findings = [
                {
                    "rule_code": f.rule_code,
                    "severity": f.severity,
                    "message": f.message,
                    "evidence": f.evidence,
                }
                for f in s.query(RuleFinding).filter_by(case_id=case.id).all()
            ]

            result = ai_assistant.diagnose(
                symptom=case.symptom,
                topology_notes=case.topology_notes,
                show_output=case.show_output,
                rule_findings=findings,
            )
            s.add(Diagnosis(case_id=case.id, **result))
            produced += 1
    return {"diagnoses_produced": produced}


# ---------------------------------------------------------------------------
# Stage 4 - metrics
# ---------------------------------------------------------------------------

def build_metrics():
    """Roll the tables up into the numbers the dashboard shows.

    Note on what these numbers mean: agreement is measured only over cases a
    human has actually reviewed. Unreviewed AI output is counted as pending,
    never as correct.
    """
    with session_scope() as s:
        total_cases = s.query(Case).count()
        total_rule_findings = s.query(RuleFinding).count()
        total_diagnoses = s.query(Diagnosis).count()
        reviews = s.query(Review).all()

        by_decision = {"accepted": 0, "edited": 0, "rejected": 0}
        for r in reviews:
            if r.decision in by_decision:
                by_decision[r.decision] += 1

        reviewed = len(reviews)
        pending = max(0, total_diagnoses - reviewed)

        by_fault = {}
        for case in s.query(Case).all():
            key = case.actual_fault_type or "UNLABELLED"
            by_fault[key] = by_fault.get(key, 0) + 1

        by_severity = {}
        for case in s.query(Case).all():
            key = case.severity or "unknown"
            by_severity[key] = by_severity.get(key, 0) + 1

        by_engine = {}
        for d in s.query(Diagnosis).all():
            by_engine[d.engine] = by_engine.get(d.engine, 0) + 1

        # Fault-type match: did the AI pick the same category as the label?
        matched = compared = 0
        for d in s.query(Diagnosis).all():
            case = s.get(Case, d.case_id)
            if not case or not case.actual_fault_type:
                continue
            compared += 1
            if (d.fault_type or "").upper() == case.actual_fault_type.upper():
                matched += 1

        return {
            "total_cases": total_cases,
            "total_rule_findings": total_rule_findings,
            "total_diagnoses": total_diagnoses,
            "reviewed": reviewed,
            "pending_review": pending,
            "by_decision": by_decision,
            "by_fault_type": dict(sorted(by_fault.items())),
            "by_severity": by_severity,
            "by_engine": by_engine,
            "fault_type_matched": matched,
            "fault_type_compared": compared,
            "agreement_rate": (
                round(by_decision["accepted"] / reviewed, 3) if reviewed else None
            ),
        }


def run_all():
    """Convenience: every stage in order. Used by the CLI runner."""
    return {
        "ingest": ingest_cases(),
        "rules": run_rule_checks(),
        "diagnoses": run_diagnoses(),
        "metrics": build_metrics(),
    }
