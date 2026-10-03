from __future__ import annotations

import json
import re
import unicodedata
from importlib.resources import files
from pathlib import Path

from rank_bm25 import BM25Okapi

from paracite.retrieval.protocol import Chunk

_TOKEN = re.compile(r"[a-záéíóúüñ0-9]+", re.IGNORECASE)


def tokenize(text: str) -> list[str]:
    folded = unicodedata.normalize("NFC", text.lower())
    return _TOKEN.findall(folded)


# seed.json es la demo ES. co-piloto.json es el piloto CO y no se mezcla en el seed.
_PACKAGE_CORPUS = ("seed.json", "co-piloto.json")
_STORE_CACHE: dict[tuple[str, tuple[str, ...]], LocalBm25Store] = {}


def _chunk_from_item(item: dict, public_base_url: str) -> Chunk:
    """Acepta el seed ES (`tipo`, `metadatos`) y el piloto CO (`tipo_norma`, `metadata`)."""
    chunk_id = item["id"]
    enlace = item.get("enlace_profundo") or f"{public_base_url.rstrip('/')}/corpus/{chunk_id}"
    meta = item.get("metadatos")
    if meta is None:
        meta = item.get("metadata") or {}
    if not isinstance(meta, dict):
        meta = {}
    materia = item.get("materia") or str(meta.get("materia") or "")
    tipo = item.get("tipo") or item.get("tipo_norma") or "norma"
    parrafo = item.get("parrafo") or ""
    return Chunk(
        id=chunk_id,
        tipo=str(tipo),
        jurisdiccion=str(item.get("jurisdiccion") or "ES"),
        materia=str(materia),
        cita_formal=item["cita_formal"],
        titulo=item.get("titulo") or "",
        parrafo=parrafo,
        enlace_profundo=enlace,
        metadatos=dict(meta),
        texto_completo=item.get("texto_completo") or parrafo,
    )


def chunks_from_payload(payload: dict, public_base_url: str) -> list[Chunk]:
    return [_chunk_from_item(item, public_base_url) for item in payload["chunks"]]


def _read_package_payload(name: str) -> dict:
    raw = files("paracite.corpus").joinpath(name).read_text(encoding="utf-8")
    return json.loads(raw)


class LocalBm25Store:
    """Almacén local de párrafos que imita retrieval WeKnora (top-k BM25).

    TODO: swap a WeKnoraHttpClient — este store existe para demos/CI sin Docker.
    """

    name = "local_fixture_bm25"

    def __init__(self, chunks: list[Chunk]) -> None:
        self._chunks = {c.id: c for c in chunks}
        self._ordered = chunks
        corpus = [tokenize(f"{c.titulo} {c.parrafo} {c.cita_formal}") for c in chunks]
        self._bm25 = BM25Okapi(corpus) if chunks else None

    @classmethod
    def from_seed(cls, public_base_url: str, seed_path: Path | None = None) -> LocalBm25Store:
        """Carga el corpus local.

        Sin `seed_path` (el arranque normal) lee el seed ES y el piloto CO
        empaquetados juntos. Con `seed_path` solo lee ese JSON.
        """
        if seed_path is not None:
            payload = json.loads(Path(seed_path).read_text(encoding="utf-8"))
            return cls(chunks_from_payload(payload, public_base_url))
        key = (public_base_url, _PACKAGE_CORPUS)
        cached = _STORE_CACHE.get(key)
        if cached is not None:
            return cached
        chunks: list[Chunk] = []
        for name in _PACKAGE_CORPUS:
            chunks.extend(chunks_from_payload(_read_package_payload(name), public_base_url))
        store = cls(chunks)
        _STORE_CACHE[key] = store
        return store

    def retrieve(
        self,
        tesis: str,
        *,
        jurisdiccion: str | None = "ES",
        tipos: list[str] | None = None,
        top_k: int = 40,
    ) -> list[Chunk]:
        if not self._ordered or self._bm25 is None:
            return []
        scores = self._bm25.get_scores(tokenize(tesis))
        ranked = sorted(zip(self._ordered, scores, strict=True), key=lambda x: x[1], reverse=True)
        out: list[Chunk] = []
        for chunk, score in ranked:
            if jurisdiccion is not None and chunk.jurisdiccion != jurisdiccion:
                continue
            if tipos and chunk.tipo not in tipos:
                continue
            if score <= 0:
                continue
            clone = Chunk(**{**chunk.__dict__, "retrieval_score": float(score)})
            out.append(clone)
            if len(out) >= top_k:
                break
        return out

    def get(self, chunk_id: str) -> Chunk | None:
        return self._chunks.get(chunk_id)

    def all_chunks(self) -> list[Chunk]:
        return list(self._ordered)
