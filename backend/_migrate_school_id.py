"""Migration Phase 2 — ajout de l'isolation school_id sur une base SQLite existante.

Pourquoi une « reconstruction » et pas de simples ALTER TABLE ?
SQLite ne peut pas, par ALTER TABLE :
  - transformer une clé primaire simple en clé composite (school_id, id) ;
  - ajouter des clés étrangères composites ;
  - modifier des contraintes UNIQUE.

La procédure est donc : pour chaque table de domaine touchée,
  1. renommer l'ancienne table en « <table>__old » ;
  2. laisser SQLAlchemy recréer la table avec le schéma exact des modèles
     actuels (create_all sur les tables manquantes) ;
  3. recopier les lignes de l'ancienne table, colonne school_id = 1
     (l'établissement existant devient le locataire n°1) ;
  4. supprimer l'ancienne table.

Garanties :
  - sauvegarde automatique du fichier avant toute modification ;
  - refus de s'exécuter si DATABASE_URL pointe vers PostgreSQL (prod) ;
  - refus si la base est déjà migrée (table « classes » avec school_id) ;
  - refus si le fichier est verrouillé par un autre processus (serveur dev) ;
  - table « ecole » et « email_codes » inchangées (aucune colonne nouvelle).

Usage :
    python _migrate_school_id.py [chemin_db]
    (défaut : backend/data/school.db — base locale de développement)
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.engine import make_url

# Enregistrement des modèles (métadonnées du schéma cible) puis moteur dédié.
from app.database import Base
from app import models  # noqa: F401  (effet de bord : remplit Base.metadata)

# Tables dont le schéma évolue (toutes sauf ecole et email_codes).
TABLE_A_MIGRER = [
    "classe_matiere",
    "enseignant_classe",
    "classes",
    "matieres",
    "enseignants",
    "parents",
    "eleves",
    "notes",
    "presences",
    "paiements",
    "versements",
    "annonces",
    "users",
    "enseignant_taux",
    "seances",
    "fiches_paie",
]

_COLONNE_LOCATAIRE = "school_id"


def _erreur(msg: str) -> None:
    print(f"✋ Migration refusée : {msg}")
    sys.exit(1)


def _colonnes(con: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in con.execute(f'PRAGMA table_info("{table}")').fetchall()]


def _verrou_libre(con: sqlite3.Connection) -> bool:
    """Vrai si on peut ouvrir une écriture immédiate (aucun autre processus)."""
    try:
        con.execute("BEGIN IMMEDIATE")
        con.rollback()
        return True
    except sqlite3.OperationalError:
        return False


def migrer(chemin: Path) -> None:
    """Applique la migration en place sur le fichier SQLite donné."""
    if not chemin.exists():
        _erreur(f"fichier introuvable : {chemin}")

    # --- Garde-fous -------------------------------------------------------
    from app.config import settings
    if settings.database_url.strip():
        _erreur(
            "DATABASE_URL est définie (PostgreSQL). Ce script ne migre que des "
            "fichiers SQLite locaux — jamais la production."
        )

    con = sqlite3.connect(str(chemin))
    try:
        con.execute("PRAGMA foreign_keys=OFF")
        if not _verrou_libre(con):
            _erreur(
                f"{chemin.name} est verrouillé par un autre processus "
                "(serveur de développement actif ?). Arrêtez-le puis relancez."
            )

        if "classes" in [r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")]:
            if "school_id" in _colonnes(con, "classes"):
                _erreur("la base est déjà migrée (colonne school_id présente).")

        presentes = {
            r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        cibles = [t for t in TABLE_A_MIGRER if t in presentes]
        if not cibles:
            _erreur("aucune table de domaine à migrer dans ce fichier.")
    finally:
        con.close()

    # --- Sauvegarde -------------------------------------------------------
    horodatage = datetime.now().strftime("%Y%m%d-%H%M%S")
    sauvegarde = chemin.with_name(f"{chemin.name}.bak-{horodatage}")
    src = sqlite3.connect(str(chemin))
    dst = sqlite3.connect(str(sauvegarde))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    print(f"💾 Sauvegarde : {sauvegarde.name}")

    # --- Comptages avant (contrôle de non-régression) ----------------------
    con = sqlite3.connect(str(chemin))
    con.execute("PRAGMA foreign_keys=OFF")
    avant = {
        t: con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        for t in cibles
    }
    con.close()

    # --- 1. Renommage des anciennes tables --------------------------------
    con = sqlite3.connect(str(chemin))
    con.execute("PRAGMA foreign_keys=OFF")
    try:
        for t in cibles:
            con.execute(f'ALTER TABLE "{t}" RENAME TO "{t}__old"')
        # Les index nommés (ex. ix_users_email) suivent la table renommée et
        # entreraient en collision avec la recréation : on les supprime.
        # (Les index automatiques sqlite_autoindex_* disparaîtront avec la
        # table, à la suppression de « <table>__old ».)
        index_a_supprimer = con.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND name NOT LIKE 'sqlite_autoindex_%' "
            "AND tbl_name LIKE '%__old'"
        ).fetchall()
        for (nom_index,) in index_a_supprimer:
            con.execute(f'DROP INDEX "{nom_index}"')
        con.commit()
    finally:
        con.close()

    # --- 2. Recréation du schéma cible (modèles actuels) ------------------
    moteur = create_engine(f"sqlite:///{chemin.as_posix()}")
    event.listen(moteur, "connect", lambda dbapi, _r: dbapi.execute(
        "PRAGMA foreign_keys=OFF"))

    @event.listens_for(moteur, "connect")
    def _busy(dbapi, _r):  # laisse SQLAlchemy attendre si bref verrou
        dbapi.execute("PRAGMA busy_timeout=5000")

    try:
        Base.metadata.create_all(bind=moteur)
        # Vérifie que les tables « fraîches » existent bien.
        inspecteur = inspect(moteur)
        absentes = [t for t in cibles if not inspecteur.has_table(t)]
        if absentes:
            _erreur(f"recréation impossible pour : {', '.join(absentes)}")
    finally:
        moteur.dispose()

    # --- 3. Copie des données (school_id = 1) -----------------------------
    con = sqlite3.connect(str(chemin))
    con.execute("PRAGMA foreign_keys=OFF")
    try:
        for t in cibles:
            nouvelles = _colonnes(con, t)
            anciennes = _colonnes(con, f"{t}__old")
            communes = [c for c in nouvelles if c in anciennes]
            inedites = [c for c in nouvelles if c not in anciennes]
            # Seule colonne réellement nouvelle attendue : school_id.
            if inedites and inedites != [_COLONNE_LOCATAIRE]:
                _erreur(
                    f"table {t} : colonnes inattendues {inedites} — "
                    "revoyez le script (drift de schéma)."
                )
            colonnes_copie = communes + inedites
            selecteurs = ", ".join(f'"{c}"' for c in communes)
            if inedites:
                selecteurs += ", 1" if not selecteurs else ", 1"
            liste_insert = ", ".join(f'"{c}"' for c in colonnes_copie)
            sql = (
                f'INSERT INTO "{t}" ({liste_insert}) '
                f'SELECT {selecteurs} FROM "{t}__old"'
            )
            con.execute(sql)
            con.commit()
        # --- 4. Suppression des anciennes tables ---------------------------
        for t in cibles:
            con.execute(f'DROP TABLE "{t}__old"')
        con.commit()
    finally:
        con.close()

    # --- 5. Contrôles finaux ----------------------------------------------
    con = sqlite3.connect(str(chemin))
    try:
        for t in cibles:
            apres = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            if apres != avant[t]:
                _erreur(
                    f"table {t} : {avant[t]} lignes avant, {apres} après — "
                    "copie incomplète, restaurez la sauvegarde."
                )
        ecoles = con.execute('SELECT id, nom FROM "ecole" ORDER BY id').fetchall()
        print(f"🏫 École(s) en base : {[(e[0], e[1]) for e in ecoles]}")
        for t in cibles:
            ok = _COLONNE_LOCATAIRE in _colonnes(con, t)
            print(f"  ✓ {t:<16} school_id {'présent' if ok else 'MANQUANT'} "
                  f"({avant[t]} lignes)")
    finally:
        con.close()

    print("✅ Migration terminée.")


if __name__ == "__main__":
    defaut = Path(__file__).resolve().parent / "data" / "school.db"
    migrer(Path(sys.argv[1]) if len(sys.argv) > 1 else defaut)
