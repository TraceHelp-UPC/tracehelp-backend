"""Adaptador ACL de solo lectura que extrae la recomendación de autoservicio desde triage_diagnoses (US12, T76).

Usa SQLAlchemy Core directamente sobre la tabla triage_diagnoses sin importar el contexto smart_triage,
exponiendo únicamente los campos seguros para el colaborador (sin puntajes internos, umbrales, modelo ni OCR).
"""
import uuid

from sqlalchemy import column, select, table
from sqlalchemy.orm import Session

from app.helpdesk.application.ports import (
    ISelfServiceRecommendationReader,
    SelfServiceRecommendation,
    SelfServiceSource,
)

CONFIDENCE_LABEL = "Alta coincidencia"

_triage_diagnoses = table(
    "triage_diagnoses",
    column("ticket_id"),
    column("review_status"),
    column("outcome"),
    column("summary"),
    column("steps"),
    column("best_score"),
    column("sources"),
)


class SqlAlchemySelfServiceRecommendationReader(ISelfServiceRecommendationReader):
    def __init__(self, session: Session) -> None:
        self._session = session

    def for_ticket(self, ticket_id: uuid.UUID) -> SelfServiceRecommendation | None:
        stmt = select(
            _triage_diagnoses.c.summary,
            _triage_diagnoses.c.steps,
            _triage_diagnoses.c.best_score,
            _triage_diagnoses.c.sources,
        ).where(
            _triage_diagnoses.c.ticket_id == ticket_id,
            _triage_diagnoses.c.review_status == "SELF_SERVICE_PROPOSED",
            _triage_diagnoses.c.outcome == "ANSWERED",
        )
        row = self._session.execute(stmt).one_or_none()
        if row is None:
            return None

        summary = row.summary.strip() if isinstance(row.summary, str) else ""
        if not summary:
            return None

        raw_steps = row.steps if isinstance(row.steps, list) else []
        steps = tuple(s.strip() for s in raw_steps if isinstance(s, str) and s.strip())
        if not steps:
            return None

        raw_sources = row.sources if isinstance(row.sources, list) else []
        sources = tuple(
            SelfServiceSource(
                reference=str(item.get("reference", "")).strip(),
                document_title=str(item.get("document_title", "")).strip(),
                citation=str(item.get("citation", "")).strip(),
            )
            for item in raw_sources
            if isinstance(item, dict)
            and str(item.get("reference", "")).strip()
            and str(item.get("document_title", "")).strip()
            and str(item.get("citation", "")).strip()
        )
        if not sources:
            return None

        match_percentage: int | None = None
        if row.best_score is not None:
            match_percentage = max(0, min(100, round(float(row.best_score) * 100)))

        return SelfServiceRecommendation(
            summary=summary,
            steps=steps,
            match_percentage=match_percentage,
            confidence_label=CONFIDENCE_LABEL,
            sources=sources,
        )
