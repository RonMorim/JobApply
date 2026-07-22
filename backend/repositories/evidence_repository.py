"""Repository for the evidence_records table.

Consolidates the read-only "active (non hard-expired) evidence for an
entity" query that was inlined (twice, near-identically) in
backend/api/routes/profile.py's trust-score and force-recalculate endpoints.

Does NOT cover profile_update_service.py's evidence_records writes — those
are append-only inserts inside larger, atomic multi-table transactions and
stay where they are (repository-consumer pattern).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.core.database import ENGINE
from backend.models.profile import EvidenceRecordRow


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    entity_id: str
    source_type: str
    base_weight: float
    raw_content: Optional[str]
    verified_at: str
    hard_expires_at: Optional[str]
    is_ai_assisted: bool


def get_active_for_entity(entity_id: str, now_iso: str) -> list[Evidence]:
    """
    Non hard-expired evidence for entity_id, freshest (by verified_at) first.

    "Active" = hard_expires_at is NULL, or in the future relative to now_iso.
    """
    with Session(ENGINE) as session:
        rows = (
            session.query(EvidenceRecordRow)
            .filter(
                EvidenceRecordRow.entity_id == entity_id,
                or_(
                    EvidenceRecordRow.hard_expires_at.is_(None),
                    EvidenceRecordRow.hard_expires_at > now_iso,
                ),
            )
            .order_by(EvidenceRecordRow.verified_at.desc())
            .all()
        )
        return [
            Evidence(
                evidence_id     = r.evidence_id,
                entity_id       = r.entity_id,
                source_type     = r.source_type,
                base_weight     = r.base_weight,
                raw_content     = r.raw_content,
                verified_at     = r.verified_at,
                hard_expires_at = r.hard_expires_at,
                is_ai_assisted  = bool(r.is_ai_assisted),
            )
            for r in rows
        ]
