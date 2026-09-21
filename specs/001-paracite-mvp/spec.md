# Feature Specification: ParaCite MVP

**Feature Branch**: `001-paracite-mvp`

**Created**: 2026-09-21

**Status**: Draft

**Input**: User description: "Build ParaCite MVP SaaS de citas jurídicas de precisión: POST /v1/cite, WeKnora retrieval, Jev classifier, API keys, fixtures ES Laboral/Civil, cero alucinación"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Citar una tesis con alta precisión (Priority: P1)

Un agente Legal-AI envía una tesis en lenguaje natural (p. ej. sobre despido disciplinario). ParaCite recupera párrafos candidatos del wiki jurídico, clasifica cuáles fundamentan de verdad la tesis y devuelve como máximo N citas formales con párrafo exacto, enlace profundo y score. Si nada supera el umbral, declara ausencia de match de alta confianza y no inventa fuentes.

**Why this priority**: Es el producto. Sin `/cite` no hay SaaS.

**Independent Test**: POST `/v1/cite` con tesis del corpus fixture Laboral/Civil y comprobar matches o `sin_match_alta_confianza`.

**Acceptance Scenarios**:

1. **Given** corpus fixture ES cargado y una tesis alineada con un párrafo, **When** POST `/v1/cite` con umbral 0.87, **Then** `matches` contiene solo ítems con `confianza >= 0.87`, cita `[FIXTURE]`, `parrafo_exacto` y `enlace_profundo`.
2. **Given** una tesis sin fundamento en el corpus (derecho inexistente o contrario), **When** se cita, **Then** `matches` es `[]` y `sin_match_alta_confianza` es true.
3. **Given** `jurisdiccion` omitida, **When** se cita, **Then** se aplica `ES`.
4. **Given** `max_resultados` = 1, **When** hay varios candidatos válidos, **Then** se devuelve como máximo 1 match.

---

### User Story 2 - Autenticar, limitar y consultar uso (Priority: P2)

Un integrador usa una API key Bearer. Las rutas de negocio exigen la clave. El healthcheck es público. Puede consultar `/v1/me` (plan, cuota, uso). El exceso de peticiones se rechaza con 429.

**Why this priority**: API-first comercial; sin claves no hay tenancy ni abuso controlado.

**Independent Test**: Llamar `/health` sin auth (200); `/v1/cite` sin auth (401); `/v1/me` con clave demo; ráfaga sobre el límite → 429.

**Acceptance Scenarios**:

1. **Given** ninguna cabecera Authorization, **When** GET `/health`, **Then** 200.
2. **Given** ninguna cabecera Authorization, **When** POST `/v1/cite`, **Then** 401.
3. **Given** una API key válida, **When** GET `/v1/me`, **Then** identidad, plan y rate-limit remaining.
4. **Given** se supera el límite por clave, **When** otra petición protegida, **Then** 429.

---

### User Story 3 - Ingesta stub y corpus demo (Priority: P3)

El operador arranca el servicio sin WeKnora ni Jev reales y el demo funciona gracias a un corpus seed etiquetado `[FIXTURE]` (ES Laboral/Civil). `POST /v1/ingest` está reservado a Enterprise: 501 por defecto, o cola Redis si el flag está activo.

**Why this priority**: Demo y CI no pueden depender de servicios externos.

**Independent Test**: Arranque en frío → `/cite` responde; POST `/v1/ingest` → 501 salvo flag.

**Acceptance Scenarios**:

1. **Given** solo el seed local, **When** se cita una tesis laboral conocida, **Then** hay match fixture (no citas STS presentadas como verificadas).
2. **Given** `ENABLE_INGEST` inactivo, **When** POST `/v1/ingest`, **Then** 501.
3. **Given** `ENABLE_INGEST` activo, **When** POST `/v1/ingest` con documento, **Then** 202 y acuse de cola.

---

### Edge Cases

- Tesis vacía o solo espacios → 422.
- `umbral_confianza` fuera de [0, 1] → 422.
- `max_resultados` < 1 o > 20 → 422.
- `jurisdiccion` distinta de ES en MVP → 200 con `sin_match_alta_confianza` (sin corpus).
- Clasificador Jev caído con `JEV_API_KEY` presente → fallback a mock, sin inventar citas.
- WeKnora inalcanzable → fallback al store local de chunks.
- `incluir_texto_completo=true` incluye texto extra en metadatos; `false` no lo hincha.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST exponer `POST /v1/cite` con request: `tesis` (req), `jurisdiccion` default ES, `tipos` opcional, `umbral_confianza` default 0.87, `max_resultados` default 3, `incluir_texto_completo` default false.
- **FR-002**: Response MUST incluir `request_id`, `tesis`, `matches[{id,tipo,confianza,cita_formal,parrafo_exacto,enlace_profundo,metadatos}]`, `sin_match_alta_confianza`, `tiempo_procesamiento_ms`.
- **FR-003**: System MUST filtrar matches: solo `es_cita_valida_alta_precision` y `confianza >= umbral`.
- **FR-004**: System MUST NOT devolver citas ausentes del corpus. Citas seed MUST llevar prefijo `[FIXTURE]`.
- **FR-005**: Retrieval MUST pedir top-40 chunks (WeKnora o store local BM25).
- **FR-006**: Classifier MUST implementar schema Jev: `chunk_id`, `relevancia_semantica` 0-1, `es_cita_valida_alta_precision`, `tipo_coincidencia`, `explicacion_corta` optional.
- **FR-007**: System MUST exponer `GET /health` sin auth.
- **FR-008**: System MUST exigir Bearer API key en `/v1/*` excepto health.
- **FR-009**: System MUST aplicar rate limiting por clave.
- **FR-010**: System MUST exponer `GET /v1/me` con uso y cuota.
- **FR-011**: System MUST exponer `POST /v1/ingest` stub (501 o 202 si flag).
- **FR-012**: System MUST sembrar corpus ES Laboral/Civil fixture al arrancar.
- **FR-013**: System MUST publicar OpenAPI (`/openapi.json` y artefacto en repo).
- **FR-014**: Tests MUST cubrir ≥20 tesis fixture (positivas y negativas).
- **FR-015**: Live Jev MUST usarse solo si `JEV_API_KEY` está definida; si no, mock de CI.

### Key Entities

- **Tesis**: Afirmación jurídica en lenguaje natural a fundamentar.
- **Chunk**: Párrafo indexado (norma/sentencia/doctrina) con cita formal, enlace, metadatos, jurisdicción, materia.
- **Match**: Chunk que supera umbral y clasificación de alta precisión.
- **ApiKey**: Credencial hashed, plan, límites, propietario.
- **RequestLog**: Auditoría de `/cite` (latencia, n matches, alta confianza).
- **JevClassification**: Resultado del clasificador por chunk.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Con mocks, p95 de `/cite` sobre fixtures < 800 ms en local.
- **SC-002**: 0 citas no etiquetadas como fixture en el seed; 0 matches por debajo del umbral.
- **SC-003**: ≥20 tesis de integración en verde (positivas y trampas).
- **SC-004**: OpenAPI generado coincide con FR-001/002/007/010/011.
- **SC-005**: Arranque sin Postgres/Redis/WeKnora/Jev externos sigue sirviendo `/cite` (sqlite + memoria + seed).

## Assumptions

- MVP = jurisdicción ES; otras jurisdicciones no inventan corpus.
- WeKnora Docker puede no estar disponible: interfaz + store local con TODO de swap.
- Jev es el clasificador de contrato; mock reproduce el schema.
- Laya-MLX se documenta como alternativa Apple Silicon, no se implementa.
- Leyes españolas en el seed son texto de demostración etiquetado `[FIXTURE]`, no un citador oficial.
- No se presentan ECLI/STS como verificados.
- Persistencia: SQLite por defecto; Postgres/Redis vía Compose cuando haya Docker.
- Dashboard = `/v1/me` + logs + página demo mínima para ejercitar `/cite`.
