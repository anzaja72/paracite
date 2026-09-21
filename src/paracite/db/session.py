from collections.abc import Generator

from sqlalchemy.orm import Session

from paracite.db.models import Base, make_engine, make_session_factory


class Database:
    def __init__(self, url: str) -> None:
        self.engine = make_engine(url)
        self.SessionLocal = make_session_factory(self.engine)
        Base.metadata.create_all(self.engine)

    def session(self) -> Generator[Session, None, None]:
        db = self.SessionLocal()
        try:
            yield db
        finally:
            db.close()
