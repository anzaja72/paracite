from __future__ import annotations

import hashlib
import time
import uuid
from sqlalchemy.orm import Session

from paracite.api.schemas import CiteMatch, CiteRequest, CiteResponse
from paracite.db.models import RequestLog


class CiteService:
    def __init__(self, retriever, classifier, *, retrieval_top_k: int = 40) -> None:
        self.retriever = retriever
        self.classifier = classifier
        self.retrieval_top_k = retrieval_top_k

    def cite(self, request: CiteRequest, *, db: Session | None = None, api_key_id: int | None = None) -> CiteResponse:
        started = time.perf_counter()
        request_id = str(uuid.uuid4())
        tipos = [t.value for t in request.tipos] if request.tipos else None
        chunks = self.retriever.retrieve(
            request.tesis,
            jurisdiccion=request.jurisdiccion,
            tipos=tipos,
            top_k=self.retrieval_top_k,
        )
        classifications = self.classifier.classify(request.tesis, chunks) if chunks else []
        by_id = {c.id: c for c in chunks}
        scored: list[CiteMatch] = []
        for item in classifications:
            if not item.es_cita_valida_alta_precision:
                continue
            if item.relevancia_semantica < request.umbral_confianza:
                continue
            chunk = by_id.get(item.chunk_id)
            if chunk is None:
                continue
            # La cita publicada es la del chunk recuperado. No se inventa una
            # fuente que no esté en el corpus, ni se descarta un chunk real
            # porque su cita_formal no empiece por [FIXTURE] o [WEKNORA].
            if not (chunk.cita_formal or "").strip():
                continue
            # El párrafo vacío no se publica: no hay texto normativo que citar.
            if not (chunk.parrafo or "").strip():
                continue
            metadatos = {
                **chunk.metadatos,
                "jurisdiccion": chunk.jurisdiccion,
                "materia": chunk.materia,
                "titulo": chunk.titulo,
                "tipo_coincidencia": item.tipo_coincidencia.value,
                "es_cita_valida_alta_precision": True,
                "relevancia_semantica": item.relevancia_semantica,
                "retrieval_score": chunk.retrieval_score,
                "clasificador": getattr(self.classifier, "name", "unknown"),
                "retriever": getattr(self.retriever, "name", "unknown"),
            }
            if item.explicacion_corta:
                metadatos["explicacion_corta"] = item.explicacion_corta
            if request.incluir_texto_completo:
                metadatos["texto_completo"] = chunk.texto_completo
            scored.append(
                CiteMatch(
                    id=chunk.id,
                    tipo=chunk.tipo,
                    confianza=round(item.relevancia_semantica, 4),
                    cita_formal=chunk.cita_formal,
                    parrafo_exacto=chunk.parrafo,
                    enlace_profundo=chunk.enlace_profundo,
                    metadatos=metadatos,
                )
            )
        scored.sort(key=lambda m: m.confianza, reverse=True)
        matches = scored[: request.max_resultados]
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        response = CiteResponse(
            request_id=request_id,
            tesis=request.tesis,
            matches=matches,
            sin_match_alta_confianza=len(matches) == 0,
            tiempo_procesamiento_ms=elapsed_ms,
        )
        if db is not None:
            self._log(db, response, api_key_id=api_key_id, jurisdiccion=request.jurisdiccion)
        return response

    def _log(self, db: Session, response: CiteResponse, *, api_key_id: int | None, jurisdiccion: str) -> None:
        db.add(
            RequestLog(
                request_id=response.request_id,
                api_key_id=api_key_id,
                tesis_hash=hashlib.sha256(response.tesis.encode()).hexdigest(),
                jurisdiccion=jurisdiccion,
                n_matches=len(response.matches),
                sin_match_alta_confianza=response.sin_match_alta_confianza,
                tiempo_ms=response.tiempo_procesamiento_ms,
            )
        )
        db.commit()


def usage_counts(db: Session, api_key_id: int) -> dict[str, int]:
    from datetime import datetime, timezone

    total = db.query(RequestLog).filter(RequestLog.api_key_id == api_key_id).count()
    today = datetime.now(timezone.utc).date()
    # SQLite stores naive datetimes; compare on date prefix via Python.
    rows = db.query(RequestLog).filter(RequestLog.api_key_id == api_key_id).all()
    citas_hoy = sum(1 for r in rows if r.created_at and r.created_at.date() == today)
    return {"citas_hoy": citas_hoy, "citas_total": total}
