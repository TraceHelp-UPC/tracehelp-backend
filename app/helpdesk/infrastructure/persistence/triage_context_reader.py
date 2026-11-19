"""Adaptador ACL de solo lectura hacia triage_diagnoses (US17, T79).

Consulta la tabla triage_diagnoses con SQLAlchemy Core sin importar módulos de app.smart_triage.
"""
import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.helpdesk.application.ports import ITriageContextReader, TriageContextSnapshot, TriageContextSource

_SELECT_TRIAGE_CONTEXT = text(
    """
    SELECT
        outcome,
        confidence_level,
        best_score,
        summary,
        steps,
        suggested_category,
        suggested_priority,
        ocr_legible,
        ocr_error_codes,
        ocr_text,
        sources
    FROM triage_diagnoses
    WHERE ticket_id = :ticket_id
    LIMIT 1
    """
)


class SqlAlchemyTriageContextReader(ITriageContextReader):
    def __init__(self, session: Session) -> None:
        self._session = session

    def for_ticket(self, ticket_id: uuid.UUID) -> TriageContextSnapshot | None:
        row = self._session.execute(_SELECT_TRIAGE_CONTEXT, {"ticket_id": ticket_id}).mappings().one_or_none()
        if row is None:
            return None

        raw_sources = row["sources"] or ()
        sources = tuple(
            TriageContextSource(
                reference=str(item.get("reference") or ""),
                document_title=str(item.get("document_title") or ""),
                citation=str(item.get("citation") or ""),
                similarity=float(item["similarity"]) if item.get("similarity") is not None else None,
            )
            for item in raw_sources
            if isinstance(item, dict)
        )
        return TriageContextSnapshot(
            outcome=str(row["outcome"]),
            confidence_level=str(row["confidence_level"]) if row["confidence_level"] is not None else None,
            best_score=float(row["best_score"]) if row["best_score"] is not None else None,
            summary=row["summary"],
            steps=tuple(str(step) for step in (row["steps"] or ())),
            suggested_category=str(row["suggested_category"]) if row["suggested_category"] is not None else None,
            suggested_priority=str(row["suggested_priority"]) if row["suggested_priority"] is not None else None,
            ocr_legible=row["ocr_legible"],
            ocr_error_codes=tuple(str(code) for code in (row["ocr_error_codes"] or ())),
            ocr_masked_text=row["ocr_text"],
            sources=sources,
        )
