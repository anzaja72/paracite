from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class Chunk:
    id: str
    tipo: str
    jurisdiccion: str
    materia: str
    cita_formal: str
    titulo: str
    parrafo: str
    enlace_profundo: str
    metadatos: dict[str, Any] = field(default_factory=dict)
    texto_completo: str = ""
    retrieval_score: float = 0.0


class WeKnoraClient(Protocol):
    """Interfaz de retrieval. Implementar con WeKnora real o store local.

    TODO: sustituir LocalBm25Store por WeKnoraHttpClient cuando WEKNORA_URL
    apunte a un wiki sano (POST /api/v1/knowledge-search, X-API-Key).
    """

    name: str

    def retrieve(
        self,
        tesis: str,
        *,
        jurisdiccion: str = "ES",
        tipos: list[str] | None = None,
        top_k: int = 40,
    ) -> list[Chunk]: ...

    def get(self, chunk_id: str) -> Chunk | None: ...

    def all_chunks(self) -> list[Chunk]: ...
