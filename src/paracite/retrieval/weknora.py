"""Cliente HTTP WeKnora.

TODO: activar cuando docker compose --profile weknora esté sano y
WEKNORA_URL / WEKNORA_API_KEY / WEKNORA_KB_ID estén definidos.
Endpoint: POST {WEKNORA_URL}/api/v1/knowledge-search
Auth: X-API-Key
Docs: https://github.com/Tencent/WeKnora/blob/main/docs/api/knowledge-search.md
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from paracite.retrieval.protocol import Chunk

logger = logging.getLogger(__name__)


class WeKnoraHttpClient:
    name = "weknora_http"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        knowledge_base_id: str,
        *,
        timeout: float = 8.0,
        fallback_get=None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.knowledge_base_id = knowledge_base_id
        self.timeout = timeout
        self._fallback_get = fallback_get

    def retrieve(
        self,
        tesis: str,
        *,
        jurisdiccion: str | None = "ES",
        tipos: list[str] | None = None,
        top_k: int = 40,
    ) -> list[Chunk]:
        url = f"{self.base_url}/api/v1/knowledge-search"
        headers = {"Content-Type": "application/json", "X-API-Key": self.api_key}
        body = {
            "query": tesis,
            "knowledge_base_id": self.knowledge_base_id,
            "match_count": top_k,
        }
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(url, headers=headers, json=body)
            response.raise_for_status()
            payload = response.json()
        items = payload.get("data") or payload.get("chunks") or []
        chunks: list[Chunk] = []
        for item in items[:top_k]:
            chunk = self._to_chunk(item, jurisdiccion)
            if tipos and chunk.tipo not in tipos:
                continue
            chunks.append(chunk)
        return chunks

    def get(self, chunk_id: str) -> Chunk | None:
        if self._fallback_get:
            return self._fallback_get(chunk_id)
        url = f"{self.base_url}/api/v1/chunks/by-id/{chunk_id}"
        headers = {"X-API-Key": self.api_key}
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(url, headers=headers)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return self._to_chunk(response.json().get("data") or response.json(), "ES")

    def all_chunks(self) -> list[Chunk]:
        if self._fallback_get:
            # El HTTP client no lista el wiki completo en MVP.
            return []
        return []

    def _to_chunk(self, item: dict[str, Any], jurisdiccion: str | None) -> Chunk:
        chunk_id = str(item.get("id") or item.get("chunk_id"))
        content = item.get("content") or item.get("text") or ""
        title = item.get("knowledge_title") or item.get("title") or "WeKnora chunk"
        score = float(item.get("score") or item.get("similarity") or 0)
        return Chunk(
            id=chunk_id,
            tipo=str(item.get("tipo") or "norma"),
            jurisdiccion=jurisdiccion if jurisdiccion is not None else str(item.get("jurisdiccion") or ""),
            materia=str(item.get("materia") or ""),
            cita_formal=str(item.get("cita_formal") or f"[WEKNORA] {title}"),
            titulo=title,
            parrafo=content,
            enlace_profundo=str(item.get("url") or f"{self.base_url}/chunks/{chunk_id}"),
            metadatos={"source": "weknora", "raw_score": score},
            texto_completo=content,
            retrieval_score=score,
        )


class FallbackRetriever:
    """Intenta WeKnora y cae al store local. Nunca inventa chunks."""

    def __init__(self, primary, fallback) -> None:
        self.primary = primary
        self.fallback = fallback
        self.name = f"{getattr(primary, 'name', 'primary')}+{fallback.name}"

    def retrieve(self, tesis: str, **kwargs) -> list[Chunk]:
        try:
            hits = self.primary.retrieve(tesis, **kwargs)
            if hits:
                return hits
        except Exception:
            logger.warning("WeKnora retrieve failed; using local fixture store", exc_info=True)
        return self.fallback.retrieve(tesis, **kwargs)

    def get(self, chunk_id: str) -> Chunk | None:
        found = None
        try:
            found = self.primary.get(chunk_id)
        except Exception:
            logger.warning("WeKnora get failed; using local fixture store", exc_info=True)
        return found or self.fallback.get(chunk_id)

    def all_chunks(self) -> list[Chunk]:
        local = self.fallback.all_chunks()
        return local
