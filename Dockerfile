FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

ENV PARACITE_HOST=0.0.0.0
ENV PARACITE_PORT=18741
EXPOSE 18741

CMD ["uvicorn", "paracite.main:app", "--host", "0.0.0.0", "--port", "18741"]
