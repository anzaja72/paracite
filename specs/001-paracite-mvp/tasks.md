# Tasks: ParaCite MVP

**Input**: Design documents from `/specs/001-paracite-mvp/`

## Phase 1: Setup

- [x] T001 Create src layout `src/paracite/` and `tests/`
- [x] T002 Initialize `pyproject.toml` package `paracite` (Python 3.12, FastAPI, pytest)
- [x] T003 [P] Add `.gitignore`, `.env.example`, `Dockerfile`, `docker-compose.yml`

## Phase 2: Foundational

- [x] T004 Config via pydantic-settings (`src/paracite/config.py`)
- [x] T005 [P] SQLAlchemy models + session (`src/paracite/db/`)
- [x] T006 [P] API schemas CiteRequest/Response (`src/paracite/api/schemas.py`)
- [x] T007 Seed demo API key + auth dependency (`src/paracite/auth/keys.py`)
- [x] T008 Rate limiter Redis/memory (`src/paracite/auth/rate_limit.py`)
- [x] T009 FastAPI app skeleton + `/health` (`src/paracite/main.py`)

## Phase 3: User Story 1 - /cite (P1) 🎯 MVP

- [x] T010 [P] [US1] Fixture corpus ES Laboral/Civil (`src/paracite/corpus/seed.json`)
- [x] T011 [P] [US1] `WeKnoraClient` + `LocalBm25Store` (`src/paracite/retrieval/`)
- [x] T012 [P] [US1] `PrecisionClassifier` mock + Jev HTTP (`src/paracite/classifier/`)
- [x] T013 [US1] `CiteService` pipeline retrieve→classify→threshold
- [x] T014 [US1] `POST /v1/cite` route
- [x] T015 [US1] ≥20 thesis integration tests (`tests/test_cite_theses.py`)

## Phase 4: User Story 2 - Auth, me, rate limit (P2)

- [x] T016 [US2] `GET /v1/me`
- [x] T017 [US2] Tests 401/429 (`tests/test_auth_rate_limit.py`)

## Phase 5: User Story 3 - Ingest stub + compose (P3)

- [x] T018 [US3] `POST /v1/ingest` 501/202
- [x] T019 [US3] WeKnora HTTP adapter + compose profile
- [x] T020 [US3] Demo page + logs

## Phase 6: Polish

- [x] T021 Export OpenAPI `docs/openapi.yaml`
- [x] T022 README (run, env, curls, precision gates)
- [x] T023 pytest green + uvicorn on 18741
