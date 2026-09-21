from typing import Protocol

from paracite.api.schemas import JevClassification
from paracite.retrieval.protocol import Chunk


class PrecisionClassifier(Protocol):
    """Clasificador de precisión. Contrato = schema Jev del producto.

    Implementaciones: MockPrecisionClassifier (CI) y JevHttpClient (JEV_API_KEY).
    Alternativa local Apple Silicon (no implementada): Laya-MLX — mismo schema.
    """

    name: str

    def classify(self, tesis: str, chunks: list[Chunk]) -> list[JevClassification]: ...
