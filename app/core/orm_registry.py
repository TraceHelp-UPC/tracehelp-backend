"""Importa los modelos ORM de todos los contextos para que Alembic los detecte.

Cuando un contexto agregue modelos nuevos, se importa su módulo aquí.
"""
from app.analytics.infrastructure.persistence import models as analytics_models  # noqa: F401
from app.core.database import Base
from app.helpdesk.infrastructure.persistence import models as helpdesk_models  # noqa: F401
from app.iam.infrastructure.persistence import models as iam_models  # noqa: F401
from app.knowledge.infrastructure.persistence import models as knowledge_models  # noqa: F401
from app.smart_triage.infrastructure.persistence import models as smart_triage_models  # noqa: F401

metadata = Base.metadata
