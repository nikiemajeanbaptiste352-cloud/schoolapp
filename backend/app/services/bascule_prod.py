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
    return colonne in outils.colonnes_du_schema(conn).get(table, [])


def _texte_lot(requetes: list[str]) -> str:
    """Assemble plusieurs instructions en une seule requête.

    Les instructions du plan sont écrites libres de leur point-virgule final :
    les concaténer demande donc de le rétablir, sans quoi le serveur lit
    `... SELECT * FROM public."x" ALTER TABLE ...` et refuse la suite
    (`syntax error`). `rstrip(';')` ne retire que la fin de chaque instruction,
    un point-virgule interne resterait intact.
    """
    return ";\n".join(r.strip().rstrip(";").rstrip() for r in requetes) + ";"


def _executer_lots(conn, instructions: list[str]) -> None:
    """Exécute un plan DDL/DML en un minimum d'allers-retours.

    La latence vers la base hébergée est le facteur limitant (≈ 0,3 s par
    échange, mesuré depuis la fonction déployée) : envoyer les ~160
    instructions une par une dépassait le délai maximal de la fonction.
    `psycopg` accepte plusieurs instructions dans un même envoi dès lors
    qu'aucun paramètre n'est lié — c'est le cas d'un plan DDL sans valeur.

    En cas d'échec du lot, le même lot est rejoué instruction par instruction
    (dans des points de sauvegarde, pour désigner précisément la coupable et
    documenter la panne) ; si même le rejeu réussit, le lot était victime d'un
    incident passager et l'exécution se poursuit normalement.
    """
    requetes = [r for r in instructions if not r.startswith("--")]
    if not requetes:
        return
    try:
        with conn.begin_nested():
            conn.exec_driver_sql(_texte_lot(requetes))
        return
    except Exception as erreur:  # noqa: BLE001 — rejeu de diagnostic
        erreur_lot = erreur

    coupable = None
    for requete in requetes:
        try:
            with conn.begin_nested():
                conn.exec_driver_sql(_texte_lot([requete]))
        except Exception:  # noqa: BLE001 — on cherche seulement laquelle casse
            coupable = requete
            break
    if coupable is None:
        return  # incident passager : le rejeu a tout appliqué
    raise RuntimeError(f"instruction en échec : {coupable}") from erreur_lot


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

    Les copies partent en **un seul envoi** ; si ce lot échoue, chaque table
    est reprise isolément dans un point de sauvegarde, ce qui permet d'écarter
    un objet récalcitrant tout en le signalant. Une table de l'application non
    copiable fait au contraire abandonner la bascule : mieux vaut ne rien
    entreprendre que migrer sans filet.
    """
    q = outils._q
    tables = _relations_a_sauvegarder(conn)
    if not tables:
        raise RuntimeError("aucune table lisible dans le schéma public : sauvegarde impossible")
    conn.execute(text(f"CREATE SCHEMA {q(schema)}"))
    copies = {
        t: f"CREATE TABLE {q(schema)}.{q(t)} AS SELECT * FROM public.{q(t)}"
        for t in tables
    }
    non_copiees: dict[str, str] = {}
    try:
        with conn.begin_nested():
            conn.exec_driver_sql(_texte_lot(list(copies.values())))
    except Exception:  # noqa: BLE001 — reprise table par table
        for table, requete in copies.items():
            try:
                with conn.begin_nested():
                    conn.exec_driver_sql(_texte_lot([requete]))
            except Exception as erreur:  # noqa: BLE001
                if table in Base.metadata.tables:
                    raise
                non_copiees[table] = f"{type(erreur).__name__} : {erreur}"[:200]
    copiees = [t for t in tables if t not in non_copiees]
    lignes = outils.compter_plusieurs(conn, copiees)
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
    ecarts = []
    copie = outils.compter_plusieurs(conn, sorted(lignes), schema=schema)
    for table, attendu in lignes.items():
        if copie.get(table) != attendu:
            ecarts.append(f"{table} : {attendu} lignes d'origine, {copie.get(table)} copiées")
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
    outils.oublier_releves()  # tout ce qui suit décrit l'état d'avant la bascule

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
    presentes = set(outils.tables_du_schema(conn))
    cibles = [t for t in outils.TABLES if t in presentes]
    deja = sorted(t for t in presentes if _colonne_existe(conn, t, "school_id"))
    sid = outils.controles_avant(conn, cibles)
    _etape("comptage_avant")
    avant = outils.compter_plusieurs(conn, cibles)
    _etape("plan")
    instructions = outils.plan_sql(conn, sid)
    _etape("execution")
    _executer_lots(conn, instructions)
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
    apres = outils.compter_plusieurs(conn, cibles)
    if apres != avant:
        raise RuntimeError(f"Comptages divergents : {avant} → {apres}")

    _etape("termine")
    outils.oublier_releves()  # le schéma a changé
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
            presentes = sorted(outils.tables_du_schema(conn))
            rapport["tables_presentes"] = presentes
            if "classes" not in presentes:
                return _noter(statut="ignore", raison="base neuve : rien à faire")
            colonnes = outils.colonnes_du_schema(conn)
            rapport["colonnes_school_id_presentes"] = sorted(
                t for t in presentes if "school_id" in colonnes.get(t, [])
            )
            if "school_id" in colonnes.get("classes", []):
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
    outils.oublier_releves()  # lecture fraîche : ce diagnostic suit la bascule
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
                "school_id" in outils.colonnes_du_schema(conn).get("classes", [])
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
                informations["lignes_sauvegarde"] = outils.compter_plusieurs(
                    conn,
                    sorted(
                        conn.execute(
                            text(
                                "SELECT table_name FROM information_schema.tables "
                                "WHERE table_schema = :s AND table_name <> '_colonnes_avant' "
                                "ORDER BY table_name"
                            ),
                            {"s": dernier},
                        ).scalars().all()
                    ),
                    schema=dernier,
                )
            informations["lignes_actuelles"] = outils.compter_plusieurs(
                conn, sorted(inspections.get_table_names())
            )
    except Exception as erreur:  # noqa: BLE001
        informations["erreur"] = f"{type(erreur).__name__} : {erreur}"
    return informations
