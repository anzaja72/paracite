"""Revisión de un documento ya generado contra el corpus cargado.

No reescribe el texto, no llama a n8n y no usa un modelo generativo.
Cada afirmación sale con un único estado: completar, dejar o no_sostiene.
La cita que se devuelve, si hace falta completarla, es la del chunk cargado.
"""

from __future__ import annotations

import hashlib
import re
import time
import unicodedata
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from paracite.api.schemas import (
    Afirmacion,
    RevisarRequest,
    RevisarResponse,
    RevisionCompletar,
    RevisionDejar,
    RevisionNoSostiene,
)
from paracite.db.models import RequestLog
from paracite.retrieval.local_store import tokenize
from paracite.retrieval.protocol import Chunk

_ART_RE = re.compile(r"\bart(?:[íi]culo|\.)?\s*(\d+(?:\.\d+)*)", re.IGNORECASE)
_CITE_PREFIX_RE = re.compile(r"^\[(?:fixture|weknora)\]\s*")
_TRAILING_NOTE_RE = re.compile(r"\s*\([^)]*\)\s*$")
_STATUTE_SPLIT_RE = re.compile(r",?\s*\bart(?:[íi]culo|\.)?\b", re.IGNORECASE)

# Palabras que aparecen en muchos títulos y no identifican una norma.
_GENERIC_STATUTE_TOKENS = {
    "código",
    "codigo",
    "ley",
    "decreto",
    "norma",
    "artículo",
    "articulo",
    "general",
    "nacional",
    "colombia",
    "colombiano",
    "colombiana",
    "política",
    "politica",
    "oficial",
}

_DEJAR = "La cita ya está completa y coincide con el párrafo del corpus. Déjala como está."
_COMPLETAR = (
    "El tema o la cita coincide con un párrafo del corpus, "
    "pero la transcripción o la cita del documento está incompleta o no es exacta."
)
_NO_SOSTIENE = "Ningún párrafo del corpus supera el umbral de confianza."


@dataclass
class _Claim:
    id: str
    surface: str


def _norm(text: str) -> str:
    folded = unicodedata.normalize("NFC", text).lower()
    return re.sub(r"\s+", " ", folded).strip()


def _fold_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def _has_published_text(chunk: Chunk) -> bool:
    """Un párrafo vacío no es cita: la fuente no trae texto y no se inventa."""
    return bool((chunk.parrafo or "").strip()) and bool((chunk.cita_formal or "").strip())


def _paragraph_body(chunk: Chunk) -> str:
    body = _norm(chunk.parrafo)
    return re.sub(r"^fixture\.\s*", "", body)


def _cite_core(chunk: Chunk) -> str:
    cite = _CITE_PREFIX_RE.sub("", _norm(chunk.cita_formal))
    return _TRAILING_NOTE_RE.sub("", cite).strip()


def _quote_exact(claim_n: str, chunk: Chunk) -> bool:
    body = _paragraph_body(chunk)
    return len(body) >= 40 and body in claim_n


def _cite_complete(claim_n: str, chunk: Chunk) -> bool:
    core = _cite_core(chunk)
    if len(core) < 8:
        return False
    start = 0
    while True:
        idx = claim_n.find(core, start)
        if idx < 0:
            return False
        # «art. 1» no es «art. 10», ni «art. 34» es «art. 34.1».
        if not _article_number_continues(claim_n, idx + len(core)):
            return True
        start = idx + 1


def _article_number_continues(claim_n: str, end: int) -> bool:
    nxt = claim_n[end:end + 1]
    if nxt.isalnum():
        return True
    return nxt in ".-" and claim_n[end + 1:end + 2].isalnum()


def _chunk_articles(chunk: Chunk) -> set[str]:
    articles: set[str] = set()
    meta = str(chunk.metadatos.get("articulo") or "").strip().lower()
    if meta:
        articles.add(meta)
    articles.update(article.lower() for article in _ART_RE.findall(_cite_core(chunk)))
    return articles


def _statute_name(chunk: Chunk) -> str:
    name = _STATUTE_SPLIT_RE.split(_cite_core(chunk), maxsplit=1)[0]
    return name.strip(" ,.-")


def _article_and_statute(claim_n: str, chunk: Chunk) -> bool:
    mentioned = {article.lower() for article in _ART_RE.findall(claim_n)}
    if not mentioned.intersection(_chunk_articles(chunk)):
        return False
    name = _statute_name(chunk)
    if len(name) >= 8 and name in claim_n:
        return True
    # «Constitución art. 29» no repite el título completo «Constitución Política».
    folded_claim = _fold_accents(claim_n)
    for token in tokenize(name):
        if len(token) < 8 or token in _GENERIC_STATUTE_TOKENS:
            continue
        if _fold_accents(token) in folded_claim:
            return True
    return False


def _in_jurisdiction(chunk: Chunk, jurisdiccion: str | None) -> bool:
    if jurisdiccion is None:
        return True
    return chunk.jurisdiccion.upper() == jurisdiccion.upper()


class RevisarService:
    def __init__(self, retriever, classifier, *, retrieval_top_k: int = 40) -> None:
        self.retriever = retriever
        self.classifier = classifier
        self.retrieval_top_k = retrieval_top_k

    def revisar(
        self,
        request: RevisarRequest,
        *,
        db: Session | None = None,
        api_key_id: int | None = None,
    ) -> RevisarResponse:
        started = time.perf_counter()
        request_id = str(uuid.uuid4())
        claims = self._claims(request)
        resultados = [self._one(claim, request) for claim in claims]
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        response = RevisarResponse(
            request_id=request_id,
            jurisdiccion=request.jurisdiccion,
            resultados=resultados,
            tiempo_procesamiento_ms=elapsed_ms,
        )
        if db is not None:
            self._log(db, response, claims, api_key_id=api_key_id)
        return response

    def _claims(self, request: RevisarRequest) -> list[_Claim]:
        if request.afirmaciones:
            return [
                self._from_afirmacion(item, index)
                for index, item in enumerate(request.afirmaciones, start=1)
            ]
        parts = re.split(r"\n\s*\n", request.texto or "")
        claims: list[_Claim] = []
        for part in parts:
            cleaned = part.strip()
            if not cleaned:
                continue
            claims.append(_Claim(id=f"a{len(claims) + 1}", surface=cleaned))
        return claims

    def _from_afirmacion(self, item: Afirmacion, index: int) -> _Claim:
        surface = item.texto if not item.cita else f"{item.texto}\n{item.cita}"
        return _Claim(id=item.id or f"a{index}", surface=surface)

    def _one(
        self, claim: _Claim, request: RevisarRequest
    ) -> RevisionCompletar | RevisionDejar | RevisionNoSostiene:
        claim_n = _norm(claim.surface)
        jurisdiccion = request.jurisdiccion
        pool: dict[str, Chunk] = {}
        for chunk in self.retriever.all_chunks():
            if _in_jurisdiction(chunk, jurisdiccion):
                pool[chunk.id] = chunk
        retrieved = self.retriever.retrieve(
            claim.surface,
            jurisdiccion=jurisdiccion,
            top_k=self.retrieval_top_k,
        )
        for chunk in retrieved:
            pool[chunk.id] = chunk

        observed = 0.0
        exact = _best_exact(claim_n, list(pool.values()))
        if exact is not None:
            chunk, dejar = exact
            confianza = 1.0 if dejar else 0.99
            observed = confianza
            if confianza >= request.umbral_confianza:
                return _matched(claim, chunk, dejar=dejar, confianza=confianza)

        best_score = observed
        best: tuple[float, Chunk] | None = None
        if retrieved:
            by_id = {chunk.id: chunk for chunk in retrieved}
            for item in self.classifier.classify(claim.surface, retrieved):
                score = float(item.relevancia_semantica)
                best_score = max(best_score, score)
                if not item.es_cita_valida_alta_precision or score < request.umbral_confianza:
                    continue
                chunk = by_id.get(item.chunk_id)
                if chunk is None or not _has_published_text(chunk):
                    continue
                if best is None or score > best[0]:
                    best = (score, chunk)
        if best is None:
            return _no_sostiene(claim, best_score)
        score, chunk = best
        dejar = _quote_exact(claim_n, chunk) and _cite_complete(claim_n, chunk)
        return _matched(claim, chunk, dejar=dejar, confianza=score)

    def _log(
        self,
        db: Session,
        response: RevisarResponse,
        claims: list[_Claim],
        *,
        api_key_id: int | None,
    ) -> None:
        joined = "\n".join(claim.surface for claim in claims)
        supported = sum(1 for item in response.resultados if item.estado != "no_sostiene")
        db.add(
            RequestLog(
                request_id=response.request_id,
                api_key_id=api_key_id,
                tesis_hash=hashlib.sha256(joined.encode()).hexdigest(),
                jurisdiccion=(response.jurisdiccion or "ALL")[:8],
                n_matches=supported,
                sin_match_alta_confianza=supported == 0,
                tiempo_ms=response.tiempo_procesamiento_ms,
            )
        )
        db.commit()


def _best_exact(claim_n: str, chunks: list[Chunk]) -> tuple[Chunk, bool] | None:
    best: tuple[tuple[int, int, int, float], Chunk, bool] | None = None
    for chunk in chunks:
        if not _has_published_text(chunk):
            continue
        quote = _quote_exact(claim_n, chunk)
        cite = _cite_complete(claim_n, chunk)
        article = _article_and_statute(claim_n, chunk)
        if not (quote or cite or article):
            continue
        dejar = bool(quote and cite)
        rank = (int(dejar), int(quote), int(cite), float(chunk.retrieval_score))
        if best is None or rank > best[0]:
            best = (rank, chunk, dejar)
    if best is None:
        return None
    return best[1], best[2]


def _matched(claim: _Claim, chunk: Chunk, *, dejar: bool, confianza: float):
    rounded = round(confianza, 4)
    if dejar:
        return RevisionDejar(
            id=claim.id,
            texto=claim.surface,
            confianza=rounded,
            indicacion=_DEJAR,
        )
    return RevisionCompletar(
        id=claim.id,
        texto=claim.surface,
        confianza=rounded,
        indicacion=_COMPLETAR,
        chunk_id=chunk.id,
        cita_formal=chunk.cita_formal,
        parrafo_exacto=chunk.parrafo,
        enlace_profundo=chunk.enlace_profundo,
    )


def _no_sostiene(claim: _Claim, confianza: float) -> RevisionNoSostiene:
    capped = min(max(confianza, 0.0), 1.0)
    return RevisionNoSostiene(
        id=claim.id,
        texto=claim.surface,
        confianza=round(capped, 4),
        indicacion=_NO_SOSTIENE,
    )
