# ParaCite

API-first para agentes Legal-AI: recibes una **tesis jurídica** y devuelves el **párrafo exacto** del corpus que la fundamenta, con cita formal, enlace profundo y score. Si no hay alta confianza, **no hay cita**.

- Paquete: `paracite`
- Jurisdicción MVP: **ES** (Laboral / Civil)
- Umbral por defecto: **0.87**
- Diseño cero-alucinación: solo matches con `es_cita_valida_alta_precision` y `confianza >= umbral`
- El seed está etiquetado **`[FIXTURE]`**. No son sentencias del Tribunal Supremo verificadas.

## Arranque local

```bash
uv sync
cp .env.example .env
uv run uvicorn paracite.main:app --host 0.0.0.0 --port 18741
```

- Demo: http://127.0.0.1:18741/
- OpenAPI UI: http://127.0.0.1:18741/docs
- Spec: http://127.0.0.1:18741/openapi.json (exportada también en `docs/openapi.yaml`)

```bash
uv run pytest
```

## Ejemplo `/v1/cite`

```bash
curl -s http://127.0.0.1:18741/health

curl -s -H "Authorization: Bearer pc_demo_dev_key" \
  http://127.0.0.1:18741/v1/me

curl -s -H "Authorization: Bearer pc_demo_dev_key" \
  -H "Content-Type: application/json" \
  -d '{"tesis":"El despido disciplinario exige un incumplimiento grave y culpable del trabajador"}' \
  http://127.0.0.1:18741/v1/cite
```

Respuesta típica (recorte):

```json
{
  "request_id": "…",
  "tesis": "El despido disciplinario exige un incumplimiento grave y culpable del trabajador",
  "matches": [
    {
      "id": "fix-et-054-despido-disciplinario",
      "tipo": "norma",
      "confianza": 0.9,
      "cita_formal": "[FIXTURE] Estatuto de los Trabajadores, art. 54.1 (corpus de demostración ParaCite; no es una cita oficial verificada)",
      "parrafo_exacto": "FIXTURE. El contrato de trabajo podrá extinguirse…",
      "enlace_profundo": "http://127.0.0.1:18741/corpus/fix-et-054-despido-disciplinario",
      "metadatos": {
        "es_cita_valida_alta_precision": true,
        "tipo_coincidencia": "fundamento_directo"
      }
    }
  ],
  "sin_match_alta_confianza": false,
  "tiempo_procesamiento_ms": 12
}
```

Tesis sin fundamento en el corpus:

```bash
curl -s -H "Authorization: Bearer pc_demo_dev_key" \
  -H "Content-Type: application/json" \
  -d '{"tesis":"El trabajador tiene derecho a un año sabático retribuido obligatorio cada tres años"}' \
  http://127.0.0.1:18741/v1/cite
```

→ `matches: []`, `sin_match_alta_confianza: true`. ParaCite **no inventa** la fuente.

## Endpoints

| Método | Ruta | Auth | Notas |
|--------|------|------|--------|
| GET | `/health` | no | Liveness + backends |
| GET | `/v1/me` | Bearer | Plan, cuota, uso |
| POST | `/v1/cite` | Bearer | Producto |
| POST | `/v1/ingest` | Bearer | 501 stub; 202 si `ENABLE_INGEST=true` |
| GET | `/corpus/{id}` | no | Enlace profundo de fixtures |
| GET | `/docs` | no | Swagger |

`POST /v1/cite` request: `tesis` (req), `jurisdiccion` default `ES`, `tipos`, `umbral_confianza` default `0.87`, `max_resultados` default `3`, `incluir_texto_completo` default `false`.

## Variables de entorno

Ver `.env.example`.

| Variable | Default | Uso |
|----------|---------|-----|
| `PARACITE_DEMO_API_KEY` | `pc_demo_dev_key` | Clave Bearer de desarrollo |
| `DATABASE_URL` | `sqlite:///./paracite.db` | SQLite o Postgres |
| `REDIS_URL` | vacío | Rate limit / cola ingest; si falta, memoria |
| `RATE_LIMIT_PER_MINUTE` | `120` | Por API key |
| `ENABLE_INGEST` | `false` | Activa el stub 202 |
| `WEKNORA_URL` / `WEKNORA_API_KEY` / `WEKNORA_KB_ID` | vacío | Retrieval WeKnora; si faltan, BM25 local |
| `JEV_API_KEY` / `JEV_API_URL` / `JEV_MODEL` | mock | Clasificador live; si falta, mock de schema Jev |

## Precision gates

1. El retriever **solo** devuelve chunks del corpus (WeKnora o seed).
2. El clasificador (Jev live o mock) emite `es_cita_valida_alta_precision`.
3. CiteService publica el match **solo** si ese flag es true **y** `relevancia_semantica >= umbral` (0.87).
4. El seed **debe** llevar `[FIXTURE]` en `cita_formal`. No se fabrican ECLI/STS.

Objetivo de latencia: p95 &lt; 800 ms con mocks.

## WeKnora y Jev

- **WeKnora**: interfaz `WeKnoraClient`. Implementación local `LocalBm25Store` (TODO de swap en `src/paracite/retrieval/weknora.py`). Compose profile `weknora` usa `wechatopenai/weknora-app` cuando el entorno pueda bajar la imagen. Retrieval HTTP: `POST /api/v1/knowledge-search` con `X-API-Key`.
- **Jev**: interfaz `PrecisionClassifier` y schema `JevClassification`. Sin `JEV_API_KEY` → mock de CI. Con clave → `JevHttpClient` (TypeSafe `system_one` / noul, modelo `jev-1.13.0`) y fallback al mock si el live falla.
- **Laya-MLX**: alternativa local en Apple Silicon; **no** se implementa y **no** cambia el contrato del schema.

## Docker Compose (Postgres / Redis / WeKnora opcional)

```bash
docker compose up -d postgres redis
# DATABASE_URL=postgresql+psycopg://paracite:paracite@localhost:5433/paracite
# REDIS_URL=redis://localhost:6380/0

docker compose --profile weknora up -d   # opcional, imagen oficial Tencent/WeKnora
```

## Estructura

```
src/paracite/          # API FastAPI
  api/                 # schemas + rutas
  retrieval/           # WeKnoraClient + BM25 local
  classifier/          # Jev mock + HTTP
  corpus/seed.json     # fixtures ES Laboral/Civil
  auth/                # API keys + rate limit
specs/001-paracite-mvp/  # Spec Kit (constitution → spec → plan → tasks)
docs/openapi.yaml
tests/                 # ≥20 tesis fixture
```

Inicializado con GitHub Spec Kit (`specify init --here --integration cursor-agent`). Constitución en `.specify/memory/constitution.md`.
