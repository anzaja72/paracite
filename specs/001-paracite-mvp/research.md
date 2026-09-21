# Research: ParaCite MVP

## WeKnora

- Producto: wiki RAG self-hosted (Tencent/WeKnora), imágenes `wechatopenai/weknora-app` y compose oficial.
- Retrieval útil: `POST /api/v1/knowledge-search` (`query`, `knowledge_base_id`) y `GET .../hybrid-search`.
- Auth: `X-API-Key`.
- Decisión: `WeKnoraClient` protocol. `LocalBm25Store` default (seed JSON). `WeKnoraHttpClient` si `WEKNORA_URL` + `WEKNORA_API_KEY` + `WEKNORA_KB_ID`. Fallback al local si el HTTP falla. TODO explícito en el cliente HTTP.
- Compose: profile `weknora` documentado; no bloquear CI si no hay Docker/imágenes.

## Jev (System One / TypeSafe)

- Modelo de decisión `jev-1.13.0`; noul 0-1 “does the section support the claim?”.
- Schema de producto (no el wire de TypeSafe): `chunk_id`, `relevancia_semantica`, `es_cita_valida_alta_precision`, `tipo_coincidencia`, `explicacion_corta`.
- Decisión: `PrecisionClassifier` protocol. `MockPrecisionClassifier` para CI (overlap + contradicciones + umbral). `JevHttpClient` si `JEV_API_KEY` (`JEV_API_URL` default `https://api.typesafe.ai/v1/system_one`). Fallback a mock si el live falla. Laya-MLX solo en README.

## Auth y rate limit

- API keys opacas `pc_...`, hash SHA-256 en DB.
- Clave demo por `PARACITE_DEMO_API_KEY`.
- Rate limit sliding window por clave (Redis si `REDIS_URL`, si no memoria proceso).
- `/health` público.

## Persistencia

- SQLAlchemy 2. SQLite default (`sqlite:///./paracite.db`). Postgres si `DATABASE_URL`.
- Tablas: users, api_keys, request_logs.
- Redis: rate limit + cola ingest.

## Corpus fixture

- ~24 chunks ES Laboral (ET-inspirado) y Civil (CC-inspirado).
- `cita_formal` siempre `[FIXTURE] ...`. Sin ECLI/STS “reales”.
- Campos `holds` / `rejects_if` para el mock de alta precisión.

## OpenAPI

- FastAPI genera `/openapi.json`. Export a `docs/openapi.yaml` en tests/CI.
