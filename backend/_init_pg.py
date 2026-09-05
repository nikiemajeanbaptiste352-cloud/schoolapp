# -*- coding: utf-8 -*-
"""Initialisation de la base PostgreSQL cible (Supabase / Vercel).

Usage — définir DATABASE_URL (jamais dans le code) puis exécuter :
    set DATABASE_URL=postgresql://user:mdp@hote:5432/postgres
    .venv\\Scripts\\python.exe -X utf8 _init_pg.py

- NON destructif : crée uniquement les tables manquantes (idempotent,
  sans suppression de données existantes).
- Insère le compte administrateur initial s'il n'existe encore aucun
  utilisateur (seed_bootstrap) : admin@lesavoir.edu / Savoir2026!

Sans DATABASE_URL définie, le script cible par erreur SQLite local :
on refuse donc de s'exécuter hors PostgreSQL.
"""
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE)
# Force le mode données réelles (jamais de seed de démonstration ici)
os.environ.pop("SEED_DEMO", None)
sys.path.insert(0, BASE)

from sqlalchemy import text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from app import models  # noqa: E402,F401  (enregistre les tables)
from app.config import settings  # noqa: E402
from app.database import Base, SessionLocal, engine, init_db  # noqa: E402
from app.seed import seed_bootstrap  # noqa: E402


def main() -> None:
    url = make_url(settings.engine_url)
    if url.get_backend_name() != "postgresql":
        print("[ABANDON] DATABASE_URL doit pointer vers PostgreSQL.")
        print("Exemple : postgresql://user:mdp@hote:5432/postgres")
        sys.exit(1)

    print(f"[i] Connexion PostgreSQL : {url.host}/{url.database}")
    init_db()  # crée les tables manquantes uniquement (idempotent)

    db = SessionLocal()
    try:
        cree = seed_bootstrap(db)  # admin@lesavoir.edu si aucun utilisateur
    finally:
        db.close()

    with engine.connect() as conn:
        tables = sorted(Base.metadata.tables.keys())
        print("Tables vérifiées :", ", ".join(tables))
        print("---")
        for t in tables:
            n = conn.execute(text('SELECT COUNT(*) FROM "' + t + '"')).scalar()
            print(f"{t}: {n} ligne(s)")
    print("---")
    if cree:
        print("[OK] Compte administrateur initial créé : admin@lesavoir.edu")
        print("     Mot de passe : Savoir2026!  (à changer après 1re connexion)")
    else:
        print("[--] Un utilisateur existait déjà : aucun compte ajouté.")


if __name__ == "__main__":
    main()
