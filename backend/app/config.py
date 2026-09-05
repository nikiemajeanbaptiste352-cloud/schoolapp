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

    # Base de données locale (SQLite)
    db_name: str = "school.db"

    # En production (déploiement Vercel) : URL PostgreSQL complète fournie par
    # la variable d'environnement DATABASE_URL (ex. Supabase) :
    #   postgresql://user:motdepasse@hôte:5432/postgres
    # Vide (défaut) → moteur SQLite local dans backend/data/{db_name}.
    database_url: str = ""

    # True (SEED_DEMO=1) → réinjecte le jeu de démonstration fictif à chaque
    # démarrage (utilisé par les tests pytest uniquement).
    # False (défaut) → base vierge : seul le compte administrateur initial
    # est créé s'il n'existe encore aucun utilisateur.
    seed_demo: bool = False

    # --- Connexion par code envoyé par email (sans mot de passe) -----------
    # Expéditeur visible : simple email OU « Nom <email> » (ex. Gmail).
    email_from: str = ""
    code_expire_minutes: int = 10
    code_longueur: int = 6
    # Fournisseur SMTP (ex. Gmail : smtp.gmail.com + mot de passe d'application)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    # OU fournisseur Resend (clé API https://resend.com/api-keys)
    resend_api_key: str = ""

    # --- Connexion « Se connecter avec Google » (OAuth 2.0) ----------------
    google_client_id: str = ""
    google_client_secret: str = ""
    # URI de redirection exacte (doit être déclarée dans Google Cloud).
    # Vide → calculée automatiquement depuis la requête (localhost / Vercel).
    google_redirect_uri: str = ""

    @property
    def google_active(self) -> bool:
        """Vrai si les identifiants OAuth Google sont présents."""
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def email_active(self) -> bool:
        """Vrai si un fournisseur d'email (Resend ou SMTP) est configuré."""
        if not self.email_from:
            return False
        if self.resend_api_key:
            return True
        return bool(self.smtp_host and self.smtp_user and self.smtp_pass)

    @property
    def db_path(self) -> Path:
        return BACKEND_DIR / "data" / self.db_name

    @property
    def engine_url(self) -> str:
        """URL SQLAlchemy effective.

        Si DATABASE_URL est définie (production Vercel), on l'utilise telle
        quelle ; sinon repli sur le fichier SQLite local (dev + tests pytest).
        Le driver PostgreSQL installé est psycopg v3 : on explicite son
        dialecte quand l'URL Supabase arrive en « postgresql://… » brut.
        """
        url = self.database_url.strip() if self.database_url else ""
        if url:
            if url.startswith("postgresql://"):
                return url.replace("postgresql://", "postgresql+psycopg://", 1)
            return url
        # Windows : chemin absolu requis par SQLAlchemy pour sqlite:///
        return f"sqlite:///{self.db_path.as_posix()}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
