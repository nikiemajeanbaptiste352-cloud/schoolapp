# -*- coding: utf-8 -*-
"""Bascule du schéma Phase 2 + 3, exécutée par l'application elle-même.

Pourquoi ce module existe
-------------------------
La chaîne de connexion de production est un secret détenu par la plateforme
d'hébergement : la variable est marquée « sensitive », l'API la restitue vide
et la CLI du poste ne la conserve pas. Aucun outil extérieur ne peut donc
atteindre la base. En revanche l'application déployée possède cette variable
au moment de son exécution : c'est le seul composant capable d'appliquer le
changement de schéma. Ce module est ce chemin.

Il ne réimplémente pas la logique : il réutilise, telles quelles, les
fonctions du script `backend/_migrate_school_id_pg.py`, déjà éprouvées sur un
bac à sable PostgreSQL (748 lignes, aucune perte, marche arrière vérifiée).

Déroulé (ordre strict)
----------------------
  1. Ne rien faire si le moteur n'est pas PostgreSQL (base locale SQLite).
  2. Ne rien faire si la table `classes` n'existe pas (base neuve : `create_all`
     s'en charge).
  3. Ne rien faire si `classes.school_id` existe déjà (base déjà convertie).
  4. Prendre un verrou consultatif PostgreSQL : une seule instance migre, les
     démarrages simultanés (plusieurs instances serverless) attendent puis
     constatent que c'est déjà fait.
  5. **Sauvegarder d'abord** : chaque table publique est recopiée telle quelle
     dans un schéma `sauvegarde_AAAAMMJJ_HHMMSS`, avec la description des
     colonnes d'origine. La sauvegarde est vérifiée ligne à ligne ; tant
     qu'elle n'est pas confirmée, rien d'autre n'est tenté.
  6. Appliquer la migration dans **une seule transaction** : toute erreur ou
     tout écart de comptage annule l'intégralité du changement.

Aucune donnée n'est supprimée à aucun moment : la migration ajoute une colonne,
remplace des contraintes et crée deux tables.
"""

from __future__ import annotations

import sys
from datetime import datetime

from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url

from app.config import BACKEND_DIR, settings
from app.database import Base, engine

# Import **statique** volontaire : un paquetage déployé ne conserve que les
# modules atteints par un import explicite. Le script de référence n'a plus
# d'effet de bord à l'import (sa préparation console a été déplacée dans
# `_preparer_sortie`, appelée par sa seule ligne de commande).
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import _migrate_school_id_pg as outils  # noqa: E402

# Identifiant arbitraire du verrou consultatif : il ne doit pas entrer en
# collision avec une autre fonctionnalité de la base.
_VERROU = 8274913042

# Dernier rapport produit par cette instance (diagnostic).
DERNIER_RAPPORT: dict = {}


def _table_existe(conn, nom: str) -> bool:
    return nom in inspect(conn).get_table_names()


def _colonne_existe(conn, table: str, colonne: str) -> bool:
    return colonne in {c["name"] for c in inspect(conn).get_columns(table)}


def _sauvegarder(conn, outils, schema: str) -> dict[str, int]:
    """Recopie toutes les tables publiques dans `schema`, puis le décrit.

    `CREATE TABLE ... AS SELECT *` conserve les données sans les interpréter :
    aucune dépendance à pg_dump (indisponible sur une plateforme serverless).
    """
    q = outils._q
    tables = sorted(inspect(conn).get_table_names())
    conn.execute(text(f"CREATE SCHEMA {q(schema)}"))
    lignes: dict[str, int] = {}
    for table in tables:
        conn.execute(
            text(f"CREATE TABLE {q(schema)}.{q(table)} AS "
                 f"SELECT * FROM public.{q(table)}")
        )
        lignes[table] = outils.compter(conn, table)
    # Description du schéma d'avant la bascule, conservée pour mémoire.
    conn.execute(
        text(
            f"CREATE TABLE {q(schema)}._colonnes_avant AS "
            "SELECT table_name, ordinal_position, column_name, data_type, "
            "       is_nullable, column_default "
            "FROM information_schema.columns "
            "WHERE table_schema = 'public' "
            "ORDER BY table_name, ordinal_position"
        )
    )
    return lignes


def _controler_sauvegarde(conn, outils, schema: str, lignes: dict[str, int]) -> list[str]:
    """Compare la copie à l'original, table par table. Renvoie les écarts."""
    q = outils._q
    ecarts = []
    for table, attendu in lignes.items():
        copie = conn.execute(
            text(f"SELECT count(*) FROM {q(schema)}.{q(table)}")
        ).scalar()
        if copie != attendu:
            ecarts.append(f"{table} : {attendu} lignes d'origine, {copie} copiées")
    return ecarts


def _migrer(outils) -> dict:
    """Applique la migration dans une transaction unique, puis recontrôle."""
    with engine.begin() as conn:
        presentes = set(inspect(conn).get_table_names())
        cibles = [t for t in outils.TABLES if t in presentes]
        sid = outils.controles_avant(conn, cibles)
        avant = {t: outils.compter(conn, t) for t in cibles}
        instructions = outils.plan_sql(conn, sid)
        for requete in instructions:
            if requete.startswith("--"):
                continue
            conn.execute(text(requete))
        # Phase 3 : `membres` et `membres_invitations`.
        nouvelles = [
            Base.metadata.tables[t]
            for t in outils.TABLES_NOUVELLES
            if t in Base.metadata.tables
        ]
        Base.metadata.create_all(bind=conn, tables=nouvelles)
        ecarts = outils.verifier_apres(conn, avant)
        if ecarts:
            raise RuntimeError(
                "Contrôle final en échec, transaction annulée :\n  - "
                + "\n  - ".join(ecarts)
            )

    # Relecture hors transaction : résultat définitif sur la base.
    with engine.connect() as conn:
        apres = {t: outils.compter(conn, t) for t in avant}
        ecarts = outils.verifier_apres(conn, avant)
    if ecarts:
        raise RuntimeError("Écarts constatés après validation : " + " ; ".join(ecarts))
    return {
        "etablissement": sid,
        "instructions": len(instructions),
        "lignes_avant": avant,
        "lignes_apres": apres,
    }


def executer_si_necessaire() -> dict:
    """Point d'entrée : convertit la base si — et seulement si — c'est utile."""
    rapport: dict = {
        "debut": datetime.now().isoformat(timespec="seconds"),
        "statut": "inconnu",
    }

    if make_url(settings.engine_url).get_backend_name() != "postgresql":
        rapport.update(statut="ignore", raison="moteur local (SQLite) : rien à faire")
        DERNIER_RAPPORT.clear()
        DERNIER_RAPPORT.update(rapport)
        return rapport

    try:
        with engine.connect() as conn:
            if not _table_existe(conn, "classes"):
                rapport.update(statut="ignore", raison="base neuve : rien à faire")
                DERNIER_RAPPORT.clear()
                DERNIER_RAPPORT.update(rapport)
                return rapport
            if _colonne_existe(conn, "classes", "school_id"):
                rapport.update(statut="deja_migre")
                DERNIER_RAPPORT.clear()
                DERNIER_RAPPORT.update(rapport)
                return rapport

        # Verrou dédié : une seule instance exécute la bascule.
        verrou = engine.connect()
        verrou.execute(text("SELECT pg_advisory_lock(:k)"), {"k": _VERROU})
        try:
            with engine.connect() as conn:
                if _colonne_existe(conn, "classes", "school_id"):
                    rapport.update(statut="deja_migre", raison="conversion faite par une autre instance")
                    return rapport

                schema = "sauvegarde_" + datetime.now().strftime("%Y%m%d_%H%M%S")
                with engine.begin() as conn:
                    lignes = _sauvegarder(conn, outils, schema)
                    ecarts = _controler_sauvegarde(conn, outils, schema, lignes)

                if ecarts:
                    raise RuntimeError(
                        "Sauvegarde non fiable, aucune modification entreprise :\n  - "
                        + "\n  - ".join(ecarts)
                    )
                rapport["sauvegarde"] = {"schema": schema, "lignes": lignes}

            resultat = _migrer(outils)
            rapport.update(statut="migre", **resultat)

        finally:
            verrou.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _VERROU})
            verrou.close()

    except Exception as erreur:  # noqa: BLE001 — on consigne au lieu d'interrompre
        rapport.update(
            statut="echec",
            erreur=f"{type(erreur).__name__} : {erreur}",
        )

    rapport["fin"] = datetime.now().isoformat(timespec="seconds")
    DERNIER_RAPPORT.clear()
    DERNIER_RAPPORT.update(rapport)
    return rapport


def resume() -> dict:
    """État constatable de la base, indépendamment de la mémoire de l'instance."""
    informations: dict = {"rapport_instance": dict(DERNIER_RAPPORT)}
    try:
        with engine.connect() as conn:
            inspections = inspect(conn)
            informations["moteur"] = (
                "postgresql"
                if make_url(settings.engine_url).get_backend_name() == "postgresql"
                else "locale"
            )
            informations["classes_school_id"] = (
                _colonne_existe(conn, "classes", "school_id")
                if _table_existe(conn, "classes")
                else None
            )
            informations["tables"] = sorted(inspections.get_table_names())
            schemas = conn.execute(
                text(
                    "SELECT schema_name FROM information_schema.schemata "
                    "WHERE schema_name LIKE 'sauvegarde\\_%' ESCAPE '\\' "
                    "ORDER BY schema_name"
                )
            ).scalars().all()
            informations["sauvegardes"] = list(schemas)
            if schemas:
                dernier = schemas[-1]
                informations["lignes_sauvegarde"] = {
                    table: conn.execute(
                        text(f'SELECT count(*) FROM "{dernier}"."{table}"')
                    ).scalar()
                    for table in sorted(
                        conn.execute(
                            text(
                                "SELECT table_name FROM information_schema.tables "
                                "WHERE table_schema = :s AND table_name <> '_colonnes_avant' "
                                "ORDER BY table_name"
                            ),
                            {"s": dernier},
                        ).scalars().all()
                    )
                }
            informations["lignes_actuelles"] = {
                table: conn.execute(text(f'SELECT count(*) FROM "{table}"')).scalar()
                for table in sorted(inspections.get_table_names())
            }
    except Exception as erreur:  # noqa: BLE001
        informations["erreur"] = f"{type(erreur).__name__} : {erreur}"
    return informations
