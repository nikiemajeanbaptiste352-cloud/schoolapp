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

import contextlib
import io
import json
import sys
import traceback
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

# Étape en cours : en cas d'échec, elle désigne l'endroit exact de la panne.
_ETAPE = "initialisation"


def _etape(nom: str) -> None:
    global _ETAPE
    _ETAPE = nom


def _table_existe(conn, nom: str) -> bool:
    return nom in inspect(conn).get_table_names()


def _colonne_existe(conn, table: str, colonne: str) -> bool:
    return colonne in {c["name"] for c in inspect(conn).get_columns(table)}


def _relations_a_sauvegarder(conn) -> list[str]:
    """Tables réelles du schéma `public`, hors objets appartenant à une extension.

    La plateforme d'hébergement ajoute ses propres objets dans `public` —
    `wrappers_fdw_stats` par exemple — qui figurent au catalogue mais que le
    rôle applicatif ne peut pas lire : les recopier fait échouer la sauvegarde
    et donc, la transaction étant unique, toute la bascule. On ne retient donc
    que les tables réelles (`relkind` r ou p) lisibles par le rôle courant et
    qui n'appartiennent pas à une extension.
    """
    return list(
        conn.execute(
            text(
                "SELECT c.relname FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') "
                "AND NOT EXISTS (SELECT 1 FROM pg_depend d "
                "                WHERE d.objid = c.oid AND d.deptype = 'e') "
                "AND has_table_privilege(c.oid, 'SELECT') "
                "ORDER BY c.relname"
            )
        ).scalars().all()
    )


def _sauvegarder(conn, outils, schema: str) -> tuple[dict[str, int], dict[str, str]]:
    """Recopie les tables publiques dans `schema`, puis décrit leurs colonnes.

    `CREATE TABLE ... AS SELECT *` conserve les données sans les interpréter :
    aucune dépendance à pg_dump (indisponible sur une plateforme serverless).
    Chaque copie passe par un point de sauvegarde : un objet récalcitrant est
    écarté et signalé, sauf s'il s'agit d'une table de l'application — auquel
    cas la bascule est abandonnée plutôt que tentée sans filet.
    """
    q = outils._q
    tables = _relations_a_sauvegarder(conn)
    if not tables:
        raise RuntimeError("aucune table lisible dans le schéma public : sauvegarde impossible")
    conn.execute(text(f"CREATE SCHEMA {q(schema)}"))
    lignes: dict[str, int] = {}
    non_copiees: dict[str, str] = {}
    for table in tables:
        try:
            with conn.begin_nested():
                conn.execute(
                    text(f"CREATE TABLE {q(schema)}.{q(table)} AS "
                         f"SELECT * FROM public.{q(table)}")
                )
        except Exception as erreur:  # noqa: BLE001
            if table in Base.metadata.tables:
                raise
            non_copiees[table] = f"{type(erreur).__name__} : {erreur}"[:200]
            continue
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
    return lignes, non_copiees


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


def _basculer_dans_transaction(conn) -> dict:
    """Sauvegarde, migration et contrôles — dans UNE SEULE transaction.

    Le verrou est pris *dans la transaction* (`pg_advisory_xact_lock`) et non
    en session : il est libéré automatiquement au commit comme à l'annulation,
    et il reste fiable derrière un répartiteur de connexions en mode
    transaction (« pooler » Supabase), où le passage par une même connexion
    n'est garanti que le temps d'une transaction.
    """
    _etape("verrou")
    conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _VERROU})

    _etape("relecture")
    if _colonne_existe(conn, "classes", "school_id"):
        return {"statut": "deja_migre", "raison": "conversion faite par une autre instance"}

    # 1. Sauvegarde intégrale, vérifiée AVANT toute modification.
    _etape("sauvegarde")
    schema = "sauvegarde_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    lignes, non_copiees = _sauvegarder(conn, outils, schema)
    _etape("controle_sauvegarde")
    ecarts = _controler_sauvegarde(conn, outils, schema, lignes)
    if ecarts:
        raise RuntimeError(
            "Sauvegarde non fiable, aucune modification entreprise :\n  - "
            + "\n  - ".join(ecarts)
        )

    # 2. Migration Phase 2 + 3, avec les fonctions déjà éprouvées.
    _etape("controles_avant")
    presentes = set(inspect(conn).get_table_names())
    cibles = [t for t in outils.TABLES if t in presentes]
    deja = sorted(t for t in presentes if _colonne_existe(conn, t, "school_id"))
    sid = outils.controles_avant(conn, cibles)
    _etape("comptage_avant")
    avant = {t: outils.compter(conn, t) for t in cibles}
    _etape("plan")
    instructions = outils.plan_sql(conn, sid)
    _etape("execution")
    for requete in instructions:
        if not requete.startswith("--"):
            conn.execute(text(requete))
    _etape("tables_nouvelles")
    nouvelles = [
        Base.metadata.tables[t]
        for t in outils.TABLES_NOUVELLES
        if t in Base.metadata.tables
    ]
    Base.metadata.create_all(bind=conn, tables=nouvelles)

    # 3. Contrôles finaux : parité de schéma, parité des lignes, aucun vide.
    _etape("verification")
    ecarts = outils.verifier_apres(conn, avant)
    if ecarts:
        raise RuntimeError(
            "Contrôle final en échec, transaction annulée :\n  - "
            + "\n  - ".join(ecarts)
        )
    _etape("comptage_apres")
    apres = {t: outils.compter(conn, t) for t in cibles}
    if apres != avant:
        raise RuntimeError(f"Comptages divergents : {avant} → {apres}")

    _etape("termine")
    return {
        "statut": "migre",
        "sauvegarde": {
            "schema": schema,
            "lignes": lignes,
            "non_copiees": non_copiees,
        },
        "etablissement": sid,
        "instructions": len(instructions),
        "colonnes_school_id_avant": deja,
        "lignes_avant": avant,
        "lignes_apres": apres,
    }


def executer_si_necessaire() -> dict:
    """Point d'entrée : convertit la base si — et seulement si — c'est utile."""
    rapport: dict = {
        "debut": datetime.now().isoformat(timespec="seconds"),
        "statut": "inconnu",
    }

    def _noter(**maj) -> dict:
        rapport.update(maj)
        rapport["fin"] = datetime.now().isoformat(timespec="seconds")
        DERNIER_RAPPORT.clear()
        DERNIER_RAPPORT.update(rapport)
        # Trace écrite dans le journal de la plateforme : c'est le seul témoin
        # consultable quand l'application ne parvient pas à démarrer.
        try:
            sys.__stdout__.write(
                "[BASCULE] " + json.dumps(rapport, ensure_ascii=False, default=str) + "\n"
            )
            sys.__stdout__.flush()
        except Exception:  # noqa: BLE001 — le journal ne doit jamais faire échouer
            pass
        return rapport

    if make_url(settings.engine_url).get_backend_name() != "postgresql":
        return _noter(statut="ignore", raison="moteur local (SQLite) : rien à faire")

    try:
        with engine.connect() as conn:
            presentes = sorted(inspect(conn).get_table_names())
            rapport["tables_presentes"] = presentes
            if "classes" not in presentes:
                return _noter(statut="ignore", raison="base neuve : rien à faire")
            rapport["colonnes_school_id_presentes"] = sorted(
                t for t in presentes if _colonne_existe(conn, t, "school_id")
            )
            if _colonne_existe(conn, "classes", "school_id"):
                return _noter(statut="deja_migre")
    except Exception as erreur:  # noqa: BLE001
        return _noter(statut="echec", erreur=f"{type(erreur).__name__} : {erreur}")

    # `_migrate_school_id_pg._echec` termine par `sys.exit(1)` : c'est un
    # `BaseException`, que `except Exception` laisse passer. On capture donc
    # tout (`BaseException`) et l'on conserve ce que le script a écrit, sinon
    # l'échec serait totalement muet.
    journal = io.StringIO()
    try:
        with contextlib.redirect_stdout(journal):
            with engine.begin() as conn:
                rapport.update(_basculer_dans_transaction(conn))
    except BaseException as erreur:  # noqa: BLE001 — consigné, jamais propagé
        rapport.update(
            statut="echec",
            etape=_ETAPE,
            erreur=f"{type(erreur).__name__} : {erreur}",
            journal=journal.getvalue()[-4000:],
            trace=traceback.format_exc()[-4000:],
        )
    return _noter()


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
            # Caractéristiques de la connexion — SANS le mot de passe : elles
            # identifient le projet Supabase réellement joint (le nom d'utilisateur
            # contient sa référence) et le mode de répartition des connexions.
            url = make_url(settings.engine_url)
            informations["connexion"] = {
                "hote": url.host,
                "port": url.port,
                "base": url.database,
                "utilisateur": url.username,
            }
            informations["serveur"] = conn.execute(text("SELECT version()")).scalar()
            informations["date_serveur"] = str(
                conn.execute(text("SELECT now()")).scalar()
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
