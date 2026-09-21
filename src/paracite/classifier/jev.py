"""Cliente live Jev (TypeSafe system_one / noul).

Si JEV_API_KEY no está, no se instancia. Si el HTTP falla, CiteService
cae al mock. El schema de salida es siempre JevClassification.
"""

from __future__ import annotations

import logging

import httpx

from paracite.api.schemas import JevClassification, TipoCoincidencia
from paracite.retrieval.protocol import Chunk

logger = logging.getLogger(__name__)

_NOUL = {
    "type": "noul",
    "instructions": "Does the section support the legal claim?",
    "criteria": {
        "true": "The section states the claim or directly implies it is true in Spanish law as written.",
        "false": "The section says nothing about the claim or states the opposite.",
    },
}


class JevHttpClient:
    name = "jev_http"

    def __init__(self, api_key: str, api_url: str, model: str, timeout: float = 12.0) -> None:
        self.api_key = api_key
        self.api_url = api_url
        self.model = model
        self.timeout = timeout

    def classify(self, tesis: str, chunks: list[Chunk]) -> list[JevClassification]:
        return [self._one(tesis, chunk) for chunk in chunks]

    def _one(self, tesis: str, chunk: Chunk) -> JevClassification:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model,
            "state": {"claim": tesis, "section": chunk.parrafo},
            "questions": {"supports": _NOUL},
        }
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(self.api_url, headers=headers, json=body)
            response.raise_for_status()
            payload = response.json()
        noul = _extract_noul(payload)
        valid = noul >= 0.87
        if noul >= 0.87:
            tipo = TipoCoincidencia.fundamento_directo
            why = "Jev noul ≥ 0.87: el párrafo soporta la tesis."
        elif noul >= 0.4:
            tipo = TipoCoincidencia.cita_parcial
            why = "Jev noul en zona de revisión; no se publica como alta precisión."
        else:
            tipo = TipoCoincidencia.no_soporta
            why = "Jev noul bajo: el párrafo no fundamenta la tesis."
        return JevClassification(
            chunk_id=chunk.id,
            relevancia_semantica=round(noul, 4),
            es_cita_valida_alta_precision=valid,
            tipo_coincidencia=tipo,
            explicacion_corta=why,
        )


def _extract_noul(payload: dict) -> float:
    answers = payload.get("answers") or {}
    supports = answers.get("supports") or payload.get("supports") or {}
    if isinstance(supports, dict):
        value = supports.get("noul")
        if value is not None:
            return max(0.0, min(1.0, float(value)))
    if "noul" in payload:
        return max(0.0, min(1.0, float(payload["noul"])))
    raise ValueError("respuesta Jev sin noul")


class FallbackClassifier:
    def __init__(self, primary, fallback) -> None:
        self.primary = primary
        self.fallback = fallback
        self.name = f"{primary.name}+{fallback.name}"

    def classify(self, tesis: str, chunks: list[Chunk]):
        try:
            return self.primary.classify(tesis, chunks)
        except Exception:
            logger.warning("Jev live failed; using mock classifier", exc_info=True)
            return self.fallback.classify(tesis, chunks)
