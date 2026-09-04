# -*- coding: utf-8 -*-
"""Remise à zéro de la base : tables vides + compte admin initial.

Usage (mode données réelles) :
    .venv\\Scripts\\python.exe -X utf8 _reset_db.py

- Supprime TOUTES les données (élèves, notes, paiements, annonces, etc.).
- Recrée les tables.
- Insère UNIQUEMENT le compte administrateur initial (seed_bootstrap).
Aucune donnée fictive n'est réinjectée.
"""
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE)
# Force le mode données réelles (jamais de seed de démonstration ici)
os.environ.pop("SEED_DEMO", None)
sys.path.insert(0, BASE)

from sqlalchemy import text  # noqa: E402

from app import models  # noqa: E402,F401  (enregistre les tables)
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.seed import seed_bootstrap  # noqa: E402


def main() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        seed_bootstrap(db)  # crée admin@lesavoir.edu si aucun utilisateur
    finally:
        db.close()

    # Comptes finaux par table
    with engine.connect() as conn:
        tables = sorted(Base.metadata.tables.keys())
        print("Tables recréées :", ", ".join(tables))
        print("---")
        for t in tables:
            n = conn.execute(text('SELECT COUNT(*) FROM "' + t + '"')).scalar()
            print(f"{t}: {n} ligne(s)")
        print("---")
        print("OK — base vide. Seul le compte administrateur initial existe.")


if __name__ == "__main__":
    main()
