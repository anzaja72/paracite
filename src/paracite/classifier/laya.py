"""Clasificación opcional con Laya Router.

Solo pregunta `noul` y `choice`. No genera un párrafo de reemplazo.
Si el paquete `laya` no está instalado, el arranque no construye el router
y /v1/revisar conserva el comportamiento anterior. El router real no se
crea hasta la primera tesis, así que importar este módulo no descarga pesos.
"""

from __future__ import annotations

import importlib.util
import logging
from typing import Any

from paracite.retrieval.protocol import Chunk

logger = logging.getLogger(__name__)

LAYA_MODEL = "multilingual"

# El piso es el umbral de producto. Por debajo no se publica una cita.
LAYA_FLOOR = 0.87

LAYA_QUESTIONS: dict[str, dict[str, Any]] = {
    "supports": {
        "type": "noul",
        "instructions": (
            "Does this paragraph state or directly imply the legal thesis? "
            "Do not write a replacement paragraph."
        ),
    },
    "relation": {
        "type": "choice",
        "instructions": (
            "How does this paragraph relate to the legal thesis? "
            "Choose one label. Do not draft text."
        ),
        "criteria": {
            "supports": "The paragraph states or directly implies the thesis.",
            "silent": "The paragraph does not address the thesis.",
            "contradicts": "The paragraph states the opposite of the thesis.",
        },
    },
}


def laya_installed() -> bool:
    return importlib.util.find_spec("laya") is not None


def laya_device(torch_module: Any | None = None) -> str:
    """mps si el backend de Apple está disponible; si no, cpu."""
    module = torch_module
    if module is None:
        try:
            import torch as module
        except ImportError:
            return "cpu"
    mps = getattr(getattr(module, "backends", None), "mps", None)
    available = getattr(mps, "is_available", None)
    if not callable(available):
        return "cpu"
    try:
        ready = bool(available())
    except (RuntimeError, OSError, AttributeError):
        return "cpu"
    return "mps" if ready else "cpu"


def laya_mode_enabled(mode: str) -> bool:
    cleaned = (mode or "auto").strip().lower()
    if cleaned in {"0", "false", "off", "no"}:
        return False
    installed = laya_installed()
    if cleaned in {"1", "true", "on", "yes"}:
        if not installed:
            logger.warning("PARACITE_LAYA está activo pero el paquete laya no está instalado")
        return installed
    return installed


def build_router(device: str | None = None):
    """Construye el Router. La descarga de pesos ocurre en el primer predict, no aquí."""
    from laya import Router

    return Router(device=device or laya_device(), preload=False, max_loaded=1)


class LayaRouterClient:
    """Puntúa párrafos ya recuperados. No redacta la cita."""

    name = "laya_router"

    def __init__(self, router=None, *, model: str = LAYA_MODEL) -> None:
        self._router = router
        self.model = model

    def score(self, tesis: str, chunks: list[Chunk]) -> list[tuple[str, float]]:
        router = self._ensure_router()
        scored: list[tuple[str, float]] = []
        for chunk in chunks:
            if not (chunk.parrafo or "").strip():
                continue
            try:
                result = router.predict(
                    {"tesis": tesis, "parrafo": chunk.parrafo},
                    LAYA_QUESTIONS,
                    model=self.model,
                )
            except Exception:
                logger.warning("Laya no pudo puntuar el chunk %s", chunk.id, exc_info=True)
                continue
            scored.append((chunk.id, support_confidence(result)))
        return scored

    def _ensure_router(self):
        if self._router is None:
            self._router = build_router()
        return self._router


def support_confidence(result: dict) -> float:
    """Confianza solo si choice es «supports» y noul es una probabilidad."""
    answers = result.get("answers") or {}
    relation = answers.get("relation") or {}
    if str(relation.get("choice") or "") != "supports":
        return 0.0
    supports = answers.get("supports") or {}
    try:
        noul = float(supports.get("noul"))
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, noul))
