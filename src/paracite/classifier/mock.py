from __future__ import annotations

import unicodedata

from paracite.api.schemas import JevClassification, TipoCoincidencia
from paracite.retrieval.local_store import tokenize
from paracite.retrieval.protocol import Chunk

_STOP = {
    "el",
    "la",
    "los",
    "las",
    "un",
    "una",
    "unos",
    "unas",
    "de",
    "del",
    "al",
    "y",
    "o",
    "en",
    "que",
    "por",
    "con",
    "se",
    "es",
    "son",
    "para",
    "su",
    "sus",
    "lo",
    "a",
    "no",
    "si",
}


def _norm(text: str) -> str:
    return unicodedata.normalize("NFC", text.lower())


def _jaccard(a: str, b: str) -> float:
    sa = {t for t in tokenize(a) if t not in _STOP and len(t) > 2}
    sb = {t for t in tokenize(b) if t not in _STOP and len(t) > 2}
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


class MockPrecisionClassifier:
    """Mock de alta calidad con el schema Jev. No llama red.

    Marca `es_cita_valida_alta_precision` solo si la tesis cubre los `holds`
    del chunk y no dispara `rejects_if`. Nunca inventa citas.
    """

    name = "jev_mock"

    def classify(self, tesis: str, chunks: list[Chunk]) -> list[JevClassification]:
        tesis_n = _norm(tesis)
        results: list[JevClassification] = []
        for chunk in chunks:
            results.append(self._one(tesis_n, tesis, chunk))
        return results

    def _one(self, tesis_n: str, tesis: str, chunk: Chunk) -> JevClassification:
        holds = [_norm(h) for h in chunk.metadatos.get("holds") or []]
        rejects = [_norm(r) for r in chunk.metadatos.get("rejects_if") or []]
        hit_reject = next((r for r in rejects if r and r in tesis_n), None)
        if hit_reject:
            return JevClassification(
                chunk_id=chunk.id,
                relevancia_semantica=round(min(0.45, 0.2 + _jaccard(tesis, chunk.parrafo)), 4),
                es_cita_valida_alta_precision=False,
                tipo_coincidencia=TipoCoincidencia.contrario,
                explicacion_corta=(
                    f"El párrafo fixture no soporta la tesis: dispara rechazo '{hit_reject}'."
                ),
            )
        hold_hits = sum(1 for h in holds if h and h in tesis_n)
        hold_ratio = hold_hits / len(holds) if holds else 0.0
        jacc = _jaccard(tesis, chunk.parrafo)
        if hold_ratio >= 0.66:
            score = round(0.88 + 0.08 * min(1.0, jacc * 2), 4)
            tipo = TipoCoincidencia.fundamento_directo
            valid = True
            why = "La tesis cubre los núcleos del párrafo fixture (fundamento directo)."
        elif hold_ratio >= 0.5 and jacc >= 0.12:
            score = round(0.74 + 0.2 * hold_ratio, 4)
            tipo = TipoCoincidencia.cita_parcial
            valid = score >= 0.87
            why = "Coincidencia parcial de núcleos; el umbral decide si se publica."
        elif jacc >= 0.22:
            score = round(min(0.72, 0.4 + jacc), 4)
            tipo = TipoCoincidencia.analogia
            valid = False
            why = "Solape léxico insuficiente para alta precisión."
        else:
            score = round(min(0.4, jacc + 0.15 * hold_ratio), 4)
            tipo = TipoCoincidencia.no_soporta
            valid = False
            why = "El chunk recuperado no fundamenta la tesis."
        if valid and not str(chunk.cita_formal).startswith("[FIXTURE]"):
            # Cinturón de seguridad: el seed MVP solo publica fixtures etiquetados.
            valid = False
            tipo = TipoCoincidencia.no_soporta
            why = "Cita no etiquetada como fixture; se omite para evitar alucinación."
        return JevClassification(
            chunk_id=chunk.id,
            relevancia_semantica=min(score, 0.97),
            es_cita_valida_alta_precision=valid and score >= 0.87,
            tipo_coincidencia=tipo,
            explicacion_corta=why,
        )
