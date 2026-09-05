"""Accès base de données — moteur SQLite ou PostgreSQL, session SQLAlchemy 2.0.

- Local (défaut) : SQLite dans backend/data/ (aucune configuration).
- Production (Vercel + Supabase) : PostgreSQL piloté par DATABASE_URL.
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    """Classe de base déclarative commune à tous les modèles."""


def _creer_moteur():
    """Crée le moteur selon l'URL effective (SQLite local ou PostgreSQL distant)."""
    url = settings.engine_url
    if make_url(url).get_backend_name() == "sqlite":
        # check_same_thread=False : nécessaire car FastAPI (threads) + SQLite
        return create_engine(
            url,
            connect_args={"check_same_thread": False},
            echo=False,
        )
    # PostgreSQL (Vercel / Supabase) : serveur distant — pool dimensionné pour
    # un environnement serverless (instances éphémères, connexions limitées).
    return create_engine(
        url,
        pool_pre_ping=True,   # évite les connexions mortes après une coupure
        pool_size=2,
        max_overflow=3,
        echo=False,
    )


engine = _creer_moteur()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    """Dépendance FastAPI : fournit une session puis la referme."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Crée les tables si elles n'existent pas.

    SQLite : crée aussi le dossier data/. PostgreSQL : aucun dossier local,
    les tables sont créées sur le serveur distant (opération idempotente).
    """
    if make_url(settings.engine_url).get_backend_name() == "sqlite":
        settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    # Import ici pour éviter les dépendances circulaires
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
