"""Adaptador de parámetros RAG desde el contexto IAM (US07, T62)."""
import uuid

from app.iam.application.workspace_settings_reader import WorkspaceSettingsReader
from app.smart_triage.application.ports import IRagParametersProvider, RagParameters


class IamRagParametersProvider(IRagParametersProvider):
    """Traduce WorkspaceSettingsReader de IAM al puerto IRagParametersProvider de Smart Triage."""

    def __init__(self, reader: WorkspaceSettingsReader) -> None:
        self._reader = reader

    def for_workspace(self, workspace_id: uuid.UUID) -> RagParameters:
        rag = self._reader.rag_for(workspace_id)
        return RagParameters(
            similarity_threshold=rag.similarity_threshold,
            self_service_threshold=rag.self_service_threshold,
            retrieval_top_k=rag.retrieval_top_k,
            strict_grounding=rag.strict_grounding,
        )
