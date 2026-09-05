"""Database tables for NetSage AI.

Four tables, mirroring the four stages of the workflow:

    Case         one broken network scenario (the input)
    RuleFinding  what the non-AI Python checker spotted
    Diagnosis    what the AI proposed
    Review       what the human decided about the AI's proposal

Keeping the AI output and the human decision in *separate* tables is
deliberate: it means we can always answer "how often was the AI right?"
without the two ever being confused for one another.
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def _now():
    return datetime.now(timezone.utc)


class Case(Base):
    """One troubleshooting scenario captured from the Packet Tracer lab."""

    __tablename__ = "cases"

    id = Column(Integer, primary_key=True)
    case_ref = Column(String(32), unique=True, nullable=False, index=True)

    symptom = Column(Text, nullable=False)
    topology_notes = Column(Text, default="")
    show_output = Column(Text, default="")

    # Ground truth: what was actually wrong. Filled in by the lab instructor
    # or by the engineer after the fix was verified.
    actual_root_cause = Column(Text, default="")
    actual_fault_type = Column(String(32), default="")   # VLAN / DHCP / DNS / ...
    actual_osi_layer = Column(String(16), default="")
    severity = Column(String(16), default="medium")      # low / medium / high

    created_at = Column(DateTime, default=_now)

    rule_findings = relationship(
        "RuleFinding", back_populates="case", cascade="all, delete-orphan"
    )
    diagnoses = relationship(
        "Diagnosis", back_populates="case", cascade="all, delete-orphan"
    )

    @property
    def latest_diagnosis(self):
        if not self.diagnoses:
            return None
        return sorted(self.diagnoses, key=lambda d: d.created_at)[-1]


class RuleFinding(Base):
    """A deterministic finding from the plain-Python rule checker.

    No AI involved. These are mechanical facts (a mask is wrong, two hosts
    share an address) that we can assert with certainty.
    """

    __tablename__ = "rule_findings"

    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False, index=True)

    rule_code = Column(String(48), nullable=False)   # e.g. DUPLICATE_IP
    severity = Column(String(16), default="medium")
    message = Column(Text, nullable=False)
    evidence = Column(Text, default="")

    created_at = Column(DateTime, default=_now)

    case = relationship("Case", back_populates="rule_findings")


class Diagnosis(Base):
    """One AI-produced proposal for a case. Never treated as final."""

    __tablename__ = "diagnoses"

    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=False, index=True)

    root_cause = Column(Text, nullable=False)
    fault_type = Column(String(32), default="")
    osi_layer = Column(String(16), default="")
    confidence = Column(Float, default=0.0)          # 0.0 - 1.0
    evidence = Column(Text, default="")
    next_command = Column(Text, default="")
    fix_steps = Column(Text, default="")

    # Which engine produced this: "claude" or "heuristic".
    engine = Column(String(24), default="heuristic")
    raw_response = Column(Text, default="")

    created_at = Column(DateTime, default=_now)

    case = relationship("Case", back_populates="diagnoses")
    review = relationship(
        "Review", back_populates="diagnosis", uselist=False,
        cascade="all, delete-orphan",
    )


class Review(Base):
    """The human decision on an AI diagnosis. This is the gate."""

    __tablename__ = "reviews"
    __table_args__ = (UniqueConstraint("diagnosis_id", name="uq_review_diagnosis"),)

    id = Column(Integer, primary_key=True)
    diagnosis_id = Column(
        Integer, ForeignKey("diagnoses.id"), nullable=False, index=True
    )

    decision = Column(String(16), nullable=False)    # accepted / edited / rejected
    reviewer = Column(String(64), default="")
    corrected_root_cause = Column(Text, default="")
    reviewer_notes = Column(Text, default="")

    created_at = Column(DateTime, default=_now)

    diagnosis = relationship("Diagnosis", back_populates="review")


DECISIONS = ("accepted", "edited", "rejected")
FAULT_TYPES = ("VLAN", "DHCP", "DNS", "ROUTING", "ACL", "NAT", "PHYSICAL", "OTHER")
