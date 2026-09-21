from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from paracite.api.schemas import IngestAccepted, IngestRequest
from paracite.db.models import IngestJob


class IngestService:
    def __init__(self, redis_client=None) -> None:
        self.redis = redis_client

    def enqueue(self, payload: IngestRequest, db: Session) -> IngestAccepted:
        job_id = str(uuid.uuid4())
        body = payload.model_dump()
        db.add(
            IngestJob(
                job_id=job_id,
                titulo=payload.titulo,
                payload=json.dumps(body, ensure_ascii=False),
                status="queued",
            )
        )
        db.commit()
        if self.redis is not None:
            try:
                self.redis.lpush("paracite:ingest", json.dumps({"job_id": job_id, **body}))
            except Exception:
                pass
        return IngestAccepted(job_id=job_id, status="queued", queued_at=datetime.now(timezone.utc))
