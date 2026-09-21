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
    def from_seed(cls, public_base_url: str, seed_path: Path | None = None) -> "LocalBm25Store":
        if seed_path is None:
            raw = files("paracite.corpus").joinpath("seed.json").read_text(encoding="utf-8")
        else:
            raw = Path(seed_path).read_text(encoding="utf-8")
        payload = json.loads(raw)
        chunks: list[Chunk] = []
        for item in payload["chunks"]:
            chunk_id = item["id"]
            enlace = item.get("enlace_profundo") or f"{public_base_url.rstrip('/')}/corpus/{chunk_id}"
            chunks.append(
                Chunk(
                    id=chunk_id,
                    tipo=item["tipo"],
                    jurisdiccion=item.get("jurisdiccion", "ES"),
                    materia=item.get("materia", ""),
                    cita_formal=item["cita_formal"],
                    titulo=item["titulo"],
                    parrafo=item["parrafo"],
                    enlace_profundo=enlace,
                    metadatos=item.get("metadatos", {}),
                    texto_completo=item.get("texto_completo") or item["parrafo"],
                )
            )
        return cls(chunks)

    def retrieve(
        self,
        tesis: str,
        *,
        jurisdiccion: str = "ES",
        tipos: list[str] | None = None,
        top_k: int = 40,
    ) -> list[Chunk]:
        if not self._ordered or self._bm25 is None:
            return []
        scores = self._bm25.get_scores(tokenize(tesis))
        ranked = sorted(zip(self._ordered, scores, strict=True), key=lambda x: x[1], reverse=True)
        out: list[Chunk] = []
        for chunk, score in ranked:
            if chunk.jurisdiccion != jurisdiccion:
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
