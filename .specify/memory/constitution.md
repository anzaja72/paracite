# ParaCite Constitution

## Core Principles

### I. Zero Alucinación (NO NEGOCIABLE)
ParaCite MUST devolver únicamente párrafos que existan en el corpus
indexado. MUST NOT generar, parafrasear como si fueran fuente, ni inventar
citas de tribunales, ECLIs, repertorios o artículos. Si no hay match por
encima del umbral, la respuesta MUST ser `sin_match_alta_confianza: true`
con `matches: []`. Toda cita de demostración MUST ir etiquetada `[FIXTURE]`.

### II. API-First y Contrato Estable
El producto es un SaaS API para agentes Legal-AI. El contrato OpenAPI de
`POST /v1/cite`, `GET /health`, `GET /v1/me` y `POST /v1/ingest` es la
fuente de verdad. Los nombres de campos del request/response (tesis,
jurisdiccion, umbral_confianza, es_cita_valida_alta_precision, etc.)
MUST conservarse. Un cambio breaking MUST versionarse bajo `/v2`.

### III. Umbral de Precisión como Puerta de Producto
El umbral por defecto MUST ser `0.87`. Un match MUST cumplir a la vez:
(1) `es_cita_valida_alta_precision == true` del clasificador y
(2) `confianza >= umbral_confianza`. El clasificador (Jev o mock) MUST
exponer el schema: chunk_id, relevancia_semantica, es_cita_valida_alta_precision,
tipo_coincidencia, explicacion_corta. Laya-MLX es nota de alternativa local,
nunca un contrato distinto.

### IV. Adaptadores Intercambiables
Retrieval (WeKnora) y clasificación (Jev) MUST ser interfaces. El MVP MAY
usar un almacén local de chunks y un mock de alta calidad cuando no haya
servicio externo. Sustituir el adaptador MUST NOT cambiar el schema HTTP.
Los TODOs de swap a WeKnora real MUST permanecer visibles en el cliente.

### V. Observabilidad, Secretos y Simplicidad
Cada `/cite` MUST registrar request_id, latencia, clave (hash), recuento
de matches y si hubo alta confianza. Los secretos MUST vivir en variables
de entorno. El MVP MUST caber en un servicio FastAPI + Postgres + Redis;
MUST NOT añadir chat, redacción de escritos ni multi-jurisdicción real.

## Stack y Límites del MVP

- Python 3.12, FastAPI, OpenAPI auto-generado.
- Jurisdicción de lanzamiento: ES. Corpus seed: Laboral y Civil, fixtures.
- Auth: `Authorization: Bearer <API_KEY>` excepto `/health`.
- Rate limiting por clave. Ingest Enterprise MAY devolver 501.
- Objetivo de latencia: p95 < 800 ms con mocks.
- WeKnora vía Docker cuando exista imagen; si no, cliente + store local.

## Flujo de Construcción (obligatorio)

1. Esqueleto FastAPI.
2. `/v1/cite` con mocks WeKnora + Jev.
3. WeKnora real vía Docker si es práctico.
4. Adaptador Jev con schema (live si `JEV_API_KEY`, si no mock).
5. API keys + rate limit.
6. ≥20 tesis fixture de integración.
7. Documentación OpenAPI.

## Governance

Esta constitución prevalece sobre preferencias ad hoc del implementador.
Toda enmienda MUST actualizar versión semántica, fecha de enmienda y
rationale. MAJOR: redefinir un principio o el contrato de cero alucinación.
MINOR: nuevo principio o ampliación material. PATCH: aclaraciones.
Los PRs y el MVP MUST evidenciar tests de tesis y el umbral 0.87.
El corpus seed MUST permanecer etiquetado como fixture.

**Version**: 1.0.0 | **Ratified**: 2026-09-21 | **Last Amended**: 2026-09-21
