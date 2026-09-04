"""Configuration centralisée du backend SchoolManager."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/  (racine du module)
BACKEND_DIR = Path(__file__).resolve().parent.parent
# Racine du projet front-end (contient index.html, pages/, css/, js/…)
FRONT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Sécurité
    secret_key: str = "dev-secret-key-a-changer-en-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480

    # Serveur
    host: str = "127.0.0.1"
    port: int = 8000

    # Base de données (SQLite)
    db_name: str = "school.db"

    # True (SEED_DEMO=1) → réinjecte le jeu de démonstration fictif à chaque
    # démarrage (utilisé par les tests pytest uniquement).
    # False (défaut) → base vierge : seul le compte administrateur initial
    # est créé s'il n'existe encore aucun utilisateur.
    seed_demo: bool = False

    @property
    def db_path(self) -> Path:
        return BACKEND_DIR / "data" / self.db_name

    @property
    def database_url(self) -> str:
        # Windows : chemin absolu requis par SQLAlchemy pour sqlite:///
        return f"sqlite:///{self.db_path.as_posix()}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
