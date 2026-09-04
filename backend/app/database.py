"""Accès base de données — moteur SQLite, session SQLAlchemy 2.0."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    """Classe de base déclarative commune à tous les modèles."""


# check_same_thread=False : nécessaire car FastAPI (threads) + SQLite
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    """Dépendance FastAPI : fournit une session puis la referme."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Crée le dossier data/ et les tables si elles n'existent pas."""
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    # Import ici pour éviter les dépendances circulaires
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
