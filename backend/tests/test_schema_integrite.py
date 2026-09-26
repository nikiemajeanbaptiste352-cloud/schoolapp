"""Intégrité du schéma — contraintes acceptables par PostgreSQL.

Pourquoi ce fichier existe (incident du 2026-09-26) : la Phase 12 a ajouté
`publications(school_id, groupe_id)` → `groupes(school_id, id)` alors que
`groupes.id` **seul** était la clé primaire. PostgreSQL refuse une clé étrangère
composite dont les colonnes visées ne forment pas une clé **unique** (erreur
42830 : « there is no unique constraint matching given keys for referenced
table »). SQLite, lui, ne l'exige pas : la suite pytest et l'E2E local étaient
verts, mais `create_all` échouait au démarrage en production et **toutes** les
routes répondaient 500 (FUNCTION_INVOCATION_FAILED).

Ce contrôle rejoue la règle de PostgreSQL sans avoir besoin d'un serveur
PostgreSQL : il inspecte les métadonnées SQLAlchemy. Toute nouvelle table
scopée par `school_id` est donc vérifiée avant d'atteindre la production.
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    ForeignKeyConstraint,
    Integer,
    MetaData,
    Table,
    UniqueConstraint,
)

import app.models  # noqa: F401 — enregistre les tables dans `Base.metadata`
from app.database import Base

TABLES_RESEAU = (
    "groupes",
    "groupes_membres",
    "publications",
    "publications_commentaires",
    "publications_reactions",
    "ressources",
)


def _cles_uniques(table) -> set[tuple[str, ...]]:
    """Colonnes ciblables par une clé étrangère : clé primaire + UNIQUE."""
    cles = {tuple(colonne.name for colonne in table.primary_key.columns)}
    for contrainte in table.constraints:
        if isinstance(contrainte, UniqueConstraint):
            cles.add(tuple(colonne.name for colonne in contrainte.columns))
    return cles


def _cles_composites_fautives(metadata) -> list[str]:
    """Clés étrangères composites dont la cible n'est pas unique.

    C'est exactement ce que PostgreSQL refuse à la création de la table.
    """
    fautives = []
    for table in metadata.tables.values():
        for fk in table.foreign_key_constraints:
            colonnes = tuple(element.column.name for element in fk.elements)
            if len(colonnes) < 2:
                continue
            cible = fk.elements[0].column.table
            if colonnes not in _cles_uniques(cible):
                fautives.append(
                    f"{table.name} {colonnes} -> {cible.name} {colonnes}"
                )
    return fautives


def _cles_simples_fautives(metadata) -> list[str]:
    """Clés étrangères à une colonne visant une colonne non unique."""
    fautives = []
    for table in metadata.tables.values():
        for fk in table.foreign_key_constraints:
            elements = list(fk.elements)
            if len(elements) != 1:
                continue
            colonne = elements[0].column
            if (colonne.name,) not in _cles_uniques(colonne.table):
                fautives.append(
                    f"{table.name}.{elements[0].parent.name}"
                    f" -> {colonne.table.name}.{colonne.name}"
                )
    return fautives


def test_le_controle_detecte_une_cle_composite_non_unique():
    """Contre-épreuve : le contrôle doit savoir dire « non ».

    On reconstruit à la main la table fautive d'origine (parent dont la clé
    primaire est `id` seul, enfant qui le référence par `(school_id, id)`).
    """
    fautif = MetaData()
    Table(
        "parent",
        fautif,
        Column("id", Integer, primary_key=True),
        Column("school_id", Integer, nullable=False),
    )
    Table(
        "enfant",
        fautif,
        Column("id", Integer, primary_key=True),
        Column("school_id", Integer, nullable=False),
        Column("parent_id", Integer, nullable=False),
        ForeignKeyConstraint(
            ["school_id", "parent_id"], ["parent.school_id", "parent.id"]
        ),
    )
    assert _cles_composites_fautives(fautif), (
        "le contrôle ne détecte pas une clé composite non unique"
    )


def test_cles_etrangeres_composites_ciblent_une_cle_unique():
    """Une clé étrangère composite doit viser un jeu de colonnes unique."""
    assert TABLES_RESEAU[0] in Base.metadata.tables, (
        "metadata vide : importer `app.models` avant de contrôler le schéma"
    )
    fautives = _cles_composites_fautives(Base.metadata)
    assert not fautives, (
        "Clé(s) étrangère(s) composite(s) refusée(s) par PostgreSQL : "
        + " ; ".join(fautives)
    )


def test_cles_etrangeres_simples_ciblent_une_colonne_unique():
    """Même règle pour les clés étrangères à une seule colonne."""
    fautives = _cles_simples_fautives(Base.metadata)
    assert not fautives, (
        "Clé(s) étrangère(s) visant une colonne non unique : "
        + " ; ".join(fautives)
    )


def test_tables_du_reseau_portent_le_school_id():
    """Les six tables du réseau scolaire sont cloisonnées par établissement."""
    for nom in TABLES_RESEAU:
        assert nom in Base.metadata.tables, f"table {nom} absente du schéma"
        table = Base.metadata.tables[nom]
        assert "school_id" in table.columns, f"{nom} sans school_id"
