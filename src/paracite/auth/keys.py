from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sqlalchemy.orm import Session

from paracite.db.models import ApiKey, User


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass
class Principal:
    key: ApiKey
    user: User
    raw_key: str


def seed_demo_key(db: Session, raw_key: str, rate_limit: int) -> ApiKey:
    digest = hash_key(raw_key)
    existing = db.query(ApiKey).filter(ApiKey.key_hash == digest).one_or_none()
    if existing:
        existing.rate_limit_per_minute = rate_limit
        existing.active = True
        db.commit()
        db.refresh(existing)
        return existing
    user = db.query(User).filter(User.nombre == "demo").one_or_none()
    if user is None:
        user = User(nombre="demo", plan="mvp")
        db.add(user)
        db.flush()
    key = ApiKey(
        user_id=user.id,
        name="demo",
        key_prefix=raw_key[:8],
        key_hash=digest,
        rate_limit_per_minute=rate_limit,
        active=True,
    )
    db.add(key)
    db.commit()
    db.refresh(key)
    return key


def resolve_key(db: Session, raw: str) -> Principal | None:
    if not raw:
        return None
    digest = hash_key(raw)
    key = db.query(ApiKey).filter(ApiKey.key_hash == digest, ApiKey.active.is_(True)).one_or_none()
    if key is None:
        return None
    return Principal(key=key, user=key.user, raw_key=raw)
