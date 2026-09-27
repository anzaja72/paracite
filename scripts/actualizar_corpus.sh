#!/usr/bin/env bash
# Actualiza el corpus colombiano desde las fuentes oficiales y publica los cambios en GitHub.
#
# Se corre desde un equipo que llegue a Función Pública (el VPS actual no llega).
# Uso manual:   ./scripts/actualizar_corpus.sh
# Semanal (Mac): ver «Carga semanal desde el Mac» en el README (launchd o crontab).
set -euo pipefail
cd "$(dirname "$0")/.."

RAMA="${PARACITE_CORPUS_BRANCH:-$(git rev-parse --abbrev-ref HEAD)}"
git pull --quiet --ff-only origin "$RAMA"

set +e
uv run python -m paracite.ingest.cargar
codigo=$?
set -e
if [ "$codigo" -ne 0 ]; then
  echo "La carga terminó con errores (ver corpus/co/manifiesto.json). No se publican cambios parciales dudosos."
fi

if git diff --quiet -- corpus/co; then
  echo "Sin cambios en el corpus."
  exit "$codigo"
fi

git add corpus/co
git commit --quiet -m "Corpus CO: actualización $(date +%Y-%m-%d)"
git push --quiet origin "$RAMA"
echo "Corpus actualizado y publicado en $RAMA."
exit "$codigo"
