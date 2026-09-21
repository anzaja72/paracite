# Implementation Plan: ParaCite MVP

**Branch**: `001-paracite-mvp` (ship on `main`) | **Date**: 2026-09-21 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-paracite-mvp/spec.md`

## Summary

SaaS API-first: FastAPI recibe una tesis, recupera top-40 párrafos (WeKnora HTTP o store BM25 local), clasifica con Jev (live o mock de schema idéntico), filtra umbral 0.87 y `es_cita_valida_alta_precision`, enriquece cita formal y responde. Auth Bearer, rate limit, seed ES Laboral/Civil `[FIXTURE]`, OpenAPI, ≥20 tests.

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**: FastAPI, Pydantic v2, uvicorn, SQLAlchemy 2, httpx, rank-bm25, redis (opcional)

**Storage**: SQLite default; Postgres + Redis via Docker Compose; corpus JSON seed on disk

**Testing**: pytest + httpx TestClient

**Target Platform**: Linux server / local uv; Netlify no aplica (API Python)

**Project Type**: web-service (FastAPI)

**Performance Goals**: p95 < 800 ms with mocks

**Constraints**: zero hallucination; threshold 0.87; no invented STS cites; secrets in env

**Scale/Scope**: MVP demo + CI; ~25 fixture chunks; 20+ thesis tests

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- Zero alucinación: CiteService never synthesizes chunk text; empty matches if gate fails. PASS
- API-first: Pydantic models = OpenAPI. PASS
- Umbral 0.87 + Jev schema: classifier protocol + filter. PASS
- Adaptadores: WeKnoraClient + PrecisionClassifier. PASS
- Simplicidad: un paquete `paracite`, sin chat. PASS

## Project Structure

### Documentation (this feature)

```text
specs/001-paracite-mvp/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/openapi.yaml
└── tasks.md
```

### Source Code (repository root)

```text
src/paracite/
├── main.py
├── config.py
├── api/schemas.py, deps.py, routes/
├── services/cite.py, ingest.py
├── retrieval/protocol.py, local_store.py, weknora.py
├── classifier/protocol.py, mock.py, jev.py
├── auth/keys.py, rate_limit.py
├── db/models.py, session.py
├── corpus/seed.json, loader.py
└── static/index.html

tests/
├── conftest.py
├── test_cite_theses.py
├── test_auth_rate_limit.py
├── test_health_me_ingest.py
└── test_openapi.py

docker-compose.yml  Dockerfile  docs/openapi.yaml
```

**Structure Decision**: Single Python package `paracite` (src layout) + pytest. Docker Compose for Postgres/Redis/WeKnora opcional.

## Complexity Tracking

Ninguna violación constitucional.
