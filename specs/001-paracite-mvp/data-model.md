# Data Model: ParaCite MVP

## Chunk (corpus, no necesariamente SQL)

- id: str (p.ej. `fix-et-054-1`)
- tipo: enum `norma` | `doctrina` | `sentencia_fixture`
- jurisdiccion: `ES`
- materia: `laboral` | `civil`
- cita_formal: str (MUST start with `[FIXTURE]`)
- titulo: str
- parrafo: str (texto exacto a devolver)
- enlace_profundo: str (URL local `/corpus/{id}` o weknora)
- metadatos: dict (articulo, norma, etiqueta_fixture, holds, rejects_if)
- texto_completo: str opcional

## User

- id, nombre, plan (`mvp`|`enterprise`), created_at

## ApiKey

- id, user_id, name, key_prefix, key_hash, rate_limit_per_minute, active, created_at

## RequestLog

- id, request_id, api_key_id, tesis_hash, jurisdiccion, n_matches, sin_match_alta_confianza, tiempo_ms, created_at

## JevMatch (ephemeral)

- chunk_id, relevancia_semantica: float 0-1, es_cita_valida_alta_precision: bool
- tipo_coincidencia: `fundamento_directo` | `cita_parcial` | `analogia` | `contrario` | `no_soporta`
- explicacion_corta: str | null

## CiteRequest / CiteResponse

Ver contracts/openapi.yaml. Defaults: jurisdiccion=ES, umbral=0.87, max_resultados=3, incluir_texto_completo=false.
