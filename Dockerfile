FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .
# Corpus real (JSONL por norma). En producción se monta como volumen para que el ingestor lo actualice.
COPY corpus ./corpus

ENV PARACITE_HOST=0.0.0.0
ENV PARACITE_PORT=18741
ENV PARACITE_CORPUS_DIR=/app/corpus
EXPOSE 18741

CMD ["uvicorn", "paracite.main:app", "--host", "0.0.0.0", "--port", "18741"]
