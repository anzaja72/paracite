# Quickstart

```bash
uv sync
cp .env.example .env
uv run uvicorn paracite.main:app --host 0.0.0.0 --port 18741
uv run pytest -q
```

```bash
curl -s http://127.0.0.1:18741/health
curl -s -H "Authorization: Bearer pc_demo_dev_key" http://127.0.0.1:18741/v1/me
curl -s -H "Authorization: Bearer pc_demo_dev_key" -H "Content-Type: application/json" \
  -d '{"tesis":"El despido disciplinario exige un incumplimiento grave y culpable del trabajador"}' \
  http://127.0.0.1:18741/v1/cite
```

Opcional: `docker compose up -d postgres redis` y `DATABASE_URL`/`REDIS_URL`. Profile `weknora` documentado en README.
