# -*- coding: utf-8 -*-
"""Migration Phase 2 + 3 — PostgreSQL (production Supabase / Vercel).

⚠️ Ce script touche des **données réelles**. Il s'exécute en **simulation par
défaut** ; il faut l'option `--appliquer` pour écrire quoi que ce soit.

    set DATABASE_URL=postgresql://...           (jamais dans le code)
    python -X utf8 _migrate_school_id_pg.py               → plan seul (rien écrit)
    python -X utf8 _migrate_school_id_pg.py --appliquer   → exécution réelle

Ce que fait la migration (une seule transaction, annulable) :

  1. Ajoute la colonne `school_id` aux 16 tables de domaine et l'affecte à
     l'établissement existant (le plus petit `ecole.id`) — l'école en place
     devient le locataire n° 1.
  2. Remplace les clés primaires « codes métier » (`id` seul) par des clés
     composites `(school_id, id)` : classes, matières, enseignants, élèves,
     annonces, barème, tables de liaison. Les codes métier (« 3A », « S1 »,
     « EL001 »…) sont conservés : le même code peut désormais exister dans
     deux écoles. Les clés étrangères **extérieures** au périmètre (portées
     par une table déjà présente en base, comme `membres`) sont retirées puis
     rétablies à l'identique, sinon PostgreSQL refuse de retirer la clé
     primaire qu'elles référencent.
  3. Remplace les clés étrangères simples par des clés composites portant le
     `school_id` (aucun croisement entre deux écoles possible).
  4. Remplace les contraintes uniques par leur version scopée
     (`(school_id, eleve_id, matiere_id, eval)` pour les notes, etc.).
  5. Crée les tables de la Phase 3 : `membres`, `membres_invitations`.

Différence avec la version SQLite (`_migrate_school_id.py`) : PostgreSQL sait
modifier une clé primaire en place, donc **pas de reconstruction de table** —
les identifiants internes et les données sont strictement préservés.

Garde-fous :
  - refuse si DATABASE_URL est absente ou non PostgreSQL (protège le SQLite local) ;
  - refuse si la base est déjà migrée (colonne `classes.school_id` présente) ;
  - refuse si la base ne correspond pas au schéma attendu avant migration
    (toute colonne inédite autre que `school_id` ou manquante) ;
  - refuse s'il n'existe aucune ligne `ecole` (impossible de choisir le locataire) ;
  - comptage des lignes avant/après : tout écart annule la transaction ;
  - `DEFAULT` posé sur `school_id` pour que **l'ancien code reste fonctionnel**
    pendant la fenêtre entre migration et déploiement (aucune écriture cassée) ;
  - vérification finale de la parité de schéma avec les modèles.
"""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path

# --- Environnement : on se place dans backend/ (imports `app.*`) -------------
BASE = Path(__file__).resolve().parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from sqlalchemy import create_engine, inspect, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.schema import UniqueConstraint  # noqa: E402

from app import models  # noqa: E402,F401  (remplit Base.metadata)
from app.config import settings  # noqa: E402
from app.database import Base  # noqa: E402


def _preparer_sortie() -> None:
    """Enveloppe UTF-8 et réglages propres à la ligne de commande.

    Ces effets sont regroupés dans une fonction — et non exécutés à l'import —
    pour que le module puisse aussi être importé par l'application (bascule
    embarquée) sans remplacer les flux de sortie de la plateforme, sans
    changer le répertoire courant et sans toucher à `SEED_DEMO`.

    ⚠️ `sys.stdout.reconfigure(encoding="utf-8")` ne suffit PAS : vérifié, le
    flux annonce alors « utf-8 » mais les octets écrits restent en cp1252.
    Seul le remplacement du flux par une enveloppe explicite agit réellement.
    """
    for _nom_flux in ("stdout", "stderr"):
        _flux = getattr(sys, _nom_flux, None)
        if getattr(_flux, "buffer", None) is None:
            continue  # flux sans tampon binaire (pythonw, flux déjà remplacé…)
        try:
            setattr(sys, _nom_flux, io.TextIOWrapper(
                _flux.buffer, encoding="utf-8", errors="replace", line_buffering=True))
        except (ValueError, AttributeError):
            pass
    os.chdir(BASE)
    # Jamais de jeu de démonstration ici : on ne touche qu'à une base réelle.
    os.environ.pop("SEED_DEMO", None)



# ---------------------------------------------------------------- Plan -------
# Les 16 tables de domaine (tout sauf `ecole` et `email_codes`).
TABLES = [
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

# Tables dont un ancien index unique plateforme doit être recréé scopé.
UNIQUES_A_REFAIRE = {"notes", "seances", "fiches_paie"}

# `users.school_id` reste nullable (compatibilité transitoire, cf. modèles).
TABLES_SCHOOL_ID_NULLABLE = {"users"}

COLONNE = "school_id"

# Nouvelles tables de la Phase 3 (créées par `create_all`, elles n'existaient
# pas dans le schéma déployé).
TABLES_NOUVELLES = ["membres", "membres_invitations"]


def _echec(msg: str) -> None:
    print(f"[ABANDON] {msg}")
    sys.exit(1)


def _q(ident: str) -> str:
    """Identifiant SQL entre guillemets (noms de tables/colonnes/contraintes)."""
    return '"' + ident.replace('"', '""') + '"'


def _liste(cols) -> str:
    return ", ".join(_q(c) for c in cols)


def _equilibre(txt: str) -> str:
    return txt.rstrip().rstrip(";") + ";"


# ------------------------------------------------- Création des instructions --
def ddl_pk(table) -> str | None:
    pk = table.primary_key
    if not pk or not list(pk.columns):
        return None
    nom = f" CONSTRAINT {_q(pk.name)}" if pk.name else ""
    return _equilibre(
        f"ALTER TABLE {_q(table.name)} ADD{nom} PRIMARY KEY "
        f"({_liste([c.name for c in pk.columns])})"
    )


def ddl_fk(table, fk) -> str:
    elements = list(fk.elements)
    parents = [e.parent.name for e in elements]
    cibles = [e.column.name for e in elements]
    ref = elements[0].column.table.name
    nom = f" CONSTRAINT {_q(fk.name)}" if fk.name else ""
    return _equilibre(
        f"ALTER TABLE {_q(table.name)} ADD{nom} FOREIGN KEY ({_liste(parents)}) "
        f"REFERENCES {_q(ref)} ({_liste(cibles)})"
    )


def ddl_unique(table, uq) -> str:
    nom = f" CONSTRAINT {_q(uq.name)}" if uq.name else ""
    return _equilibre(
        f"ALTER TABLE {_q(table.name)} ADD{nom} UNIQUE "
        f"({_liste([c.name for c in uq.columns])})"
    )


def uniques_modele(table) -> list:
    return [c for c in table.constraints if isinstance(c, UniqueConstraint)]


# ------------------------------------------------------------- Lecture base --
# Chaque aller-retour vers la base hébergée coûte cher (mesuré ≈ 0,3 s depuis
# la fonction déployée). Les relevés de schéma sont donc lus **en une requête
# par nature d'information** et mémorisés pour la durée d'une transaction.
# L'état mémorisé est celui d'AVANT la bascule : après modification, il faut
# oublier les relevés concernés (`oublier_releves`).
_RELEVES: dict = {}


def _releve(cle: str, fabrique):
    """Relevé de catalogue mémorisé (une seule requête par nature)."""
    if cle not in _RELEVES:
        _RELEVES[cle] = fabrique()
    return _RELEVES[cle]


def _litteral(txt: str) -> str:
    """Chaîne SQL entre apostrophes (apostrophes internes doublées)."""
    return "'" + str(txt).replace("'", "''") + "'"


def oublier_releves() -> None:
    """Oublie les relevés mémorisés (schéma modifié, ou nouvelle transaction)."""
    _RELEVES.clear()


def tables_du_schema(conn) -> list[str]:
    return _releve("tables", lambda: sorted(inspect(conn).get_table_names()))


def colonnes_du_schema(conn) -> dict[str, list[str]]:
    """Colonnes de toutes les tables du schéma, en UNE requête."""

    def lire() -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for table, colonne in conn.execute(
            text(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = current_schema() "
                "ORDER BY table_name, ordinal_position"
            )
        ).fetchall():
            out.setdefault(table, []).append(colonne)
        return out

    return _releve("colonnes", lire)


def colonnes_reelles(conn, table: str) -> list[str]:
    return colonnes_du_schema(conn).get(table, [])


def contraintes_du_schema(conn) -> dict[tuple[str, str], list]:
    """PK / UNIQUE / FK du schéma avec leurs colonnes (UNE requête).

    Renvoie `{(table, contrainte): [type, colonnes, table_referencee,
    colonnes_referencees]}`.
    """

    def lire() -> dict[tuple[str, str], list]:
        rows = conn.execute(
            text(
                "SELECT t.relname, c.conname, c.contype, a.attname, "
                "       rt.relname, ra.attname "
                "FROM pg_constraint c "
                "JOIN pg_class t ON t.oid = c.conrelid "
                "JOIN pg_namespace n ON n.oid = t.relnamespace "
                "JOIN unnest(c.conkey) WITH ORDINALITY AS k(attnum, ord) ON true "
                "JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.attnum "
                "LEFT JOIN pg_class rt ON rt.oid = c.confrelid "
                "LEFT JOIN unnest(c.confkey) WITH ORDINALITY AS rk(attnum, ord) "
                "     ON rk.ord = k.ord "
                "LEFT JOIN pg_attribute ra "
                "     ON ra.attrelid = c.confrelid AND ra.attnum = rk.attnum "
                "WHERE n.nspname = current_schema() "
                "  AND c.contype IN ('p', 'u', 'f') "
                "ORDER BY t.relname, c.conname, k.ord"
            )
        ).fetchall()
        out: dict[tuple[str, str], list] = {}
        for table, nom, type_, colonne, table_ref, colonne_ref in rows:
            entree = out.setdefault((table, nom), [type_, [], None, []])
            entree[1].append(colonne)
            if table_ref is not None:
                entree[2] = table_ref
                entree[3].append(colonne_ref)
        return out

    return _releve("contraintes_colonnes", lire)


def contraintes(conn, table: str) -> dict[str, list[str]]:
    """Noms des contraintes PK / FK / UNIQUE d'une table, groupés par type."""

    def lire() -> dict[str, dict[str, list[str]]]:
        out: dict[str, dict[str, list[str]]] = {}
        for (nom_table, nom), (type_, _c, _r, _rc) in contraintes_du_schema(conn).items():
            if type_ in ("p", "f", "u"):
                out.setdefault(nom_table, {"p": [], "f": [], "u": []})[type_].append(nom)
        return out

    return _releve("contraintes_par_table", lire).get(
        table, {"p": [], "f": [], "u": []}
    )


def compter(conn, table: str) -> int | None:
    try:
        return conn.execute(text(f"SELECT COUNT(*) FROM {_q(table)}")).scalar()
    except Exception:  # table absente
        return None


def compter_plusieurs(conn, tables, schema: str | None = None) -> dict[str, int | None]:
    """Nombre de lignes de plusieurs tables en UNE seule requête.

    Réduit la latence : compter 18 tables coûtait 18 allers-retours. En cas
    d'échec (table absente ou illisible), on repasse table par table pour
    conserver le comportement tolérant de `compter`.
    """
    liste = list(tables)
    if not liste:
        return {}
    prefixe = f"{_q(schema)}." if schema else ""
    bloc = " UNION ALL ".join(
        f"SELECT {_litteral(t)} AS nom, count(*) AS n FROM {prefixe}{_q(t)}"
        for t in liste
    )
    try:
        return {nom: n for nom, n in conn.execute(text(bloc)).fetchall()}
    except Exception:  # noqa: BLE001 — relevé groupé impossible, repli sûr
        return {t: compter(conn, t) for t in liste}


def fk_a_relacher(conn, cibles: list[str]) -> list[tuple[str, str, str]]:
    """Clés étrangères portées par une table HORS migration, mais pointant
    vers une table migrée.

    PostgreSQL refuse de supprimer une clé primaire tant qu'une clé étrangère
    s'appuie sur son index (`DependentObjectsStillExist`). Or les tables hors
    migration peuvent déjà exister en base (créées par le `create_all` d'un
    déploiement antérieur) : c'est le cas de `membres`, dont
    `membres_user_id_fkey` pointe vers `users.id`.

    Ces contraintes sont donc retirées avant les clés primaires, puis
    rétablies **à l'identique** : leur définition est relue dans le catalogue
    (`pg_get_constraintdef`), elle n'est pas reconstruite depuis les modèles
    (ces tables ne font pas partie du périmètre migré).

    Renvoie des triplets (table, nom de contrainte, définition SQL).
    """
    visees = set(cibles) | set(UNIQUES_A_REFAIRE)
    rows = conn.execute(
        text(
            "SELECT t.relname, c.conname, pg_get_constraintdef(c.oid), r.relname "
            "FROM pg_constraint c "
            "JOIN pg_class t ON t.oid = c.conrelid "
            "JOIN pg_namespace n ON n.oid = t.relnamespace "
            "JOIN pg_class r ON r.oid = c.confrelid "
            "WHERE n.nspname = current_schema() AND c.contype = 'f' "
            "ORDER BY t.relname, c.conname"
        )
    ).fetchall()
    return [(t, n, d) for t, n, d, ref in rows if ref in visees and t not in visees]


# --------------------------------------------------------------- Contrôles ---
def lignes_sans_school_id(conn, tables) -> dict[str, int]:
    """Lignes sans `school_id` pour plusieurs tables, en UNE requête."""
    liste = list(tables)
    if not liste:
        return {}
    bloc = " UNION ALL ".join(
        f"SELECT {_litteral(t)} AS nom, count(*) AS n FROM {_q(t)} "
        f"WHERE {_q(COLONNE)} IS NULL"
        for t in liste
    )
    try:
        return {nom: n for nom, n in conn.execute(text(bloc)).fetchall()}
    except Exception:  # noqa: BLE001 — repli table par table
        return {
            t: conn.execute(
                text(f"SELECT COUNT(*) FROM {_q(t)} WHERE {_q(COLONNE)} IS NULL")
            ).scalar()
            for t in liste
        }


def controles_avant(conn, cibles: list[str]) -> int:
    """Vérifie l'état initial et renvoie l'identifiant d'école à affecter."""
    oublier_releves()  # tout ce qui est lu ici décrit l'état d'AVANT la bascule
    presentes = set(tables_du_schema(conn))
    absentes = [t for t in cibles if t not in presentes]
    if absentes:
        _echec(f"tables manquantes en base : {', '.join(absentes)}")

    if COLONNE in colonnes_reelles(conn, "classes"):
        _echec(
            "la base semble DÉJÀ migrée (colonne classes.school_id présente). "
            "Rien n'a été fait."
        )

    # Parité de colonnes : tout écart autre que school_id = schéma inattendu.
    for t in cibles:
        attendues = set(Base.metadata.tables[t].columns.keys())
        reelles = set(colonnes_reelles(conn, t))
        en_trop = reelles - attendues
        manquantes = attendues - reelles - {COLONNE}
        if en_trop:
            _echec(
                f"table {t} : colonnes inattendues {sorted(en_trop)} — "
                "le schéma de production a dérivé, migration non appliquée."
            )
        if manquantes:
            _echec(
                f"table {t} : colonnes du modèle absentes de la base "
                f"{sorted(manquantes)} — vérifiez la version déployée."
            )

    # Établissement de référence (locataire n° 1).
    ids = conn.execute(text("SELECT id FROM ecole ORDER BY id")).fetchall()
    if not ids:
        _echec("aucune ligne dans `ecole` : impossible de choisir l'établissement.")
    sid = ids[0][0]
    if len(ids) > 1:
        print(
            f"[!] {len(ids)} établissements en base : la migration rattache "
            f"toutes les données existantes à l'école n° {sid}."
        )
    return sid


def plan_sql(conn, sid: int) -> list[str]:
    """Construit la liste ordonnée des instructions DDL/DML.

    Réutilise les relevés mémorisés par `controles_avant` : le même état
    d'avant bascule, sans nouvelle lecture du catalogue.
    """
    avant = {t: contraintes(conn, t) for t in TABLES}
    a_relacher = fk_a_relacher(conn, TABLES)
    sql: list[str] = []

    # 0. Nouvelles tables Phase 3 -------------------------------------------
    presentes = set(tables_du_schema(conn))
    for t in TABLES_NOUVELLES:
        if t not in presentes:
            sql.append(f"-- table {t} : créée par les modèles (create_all)")

    # 1. Colonne school_id ---------------------------------------------------
    for t in TABLES:
        if COLONNE not in colonnes_reelles(conn, t):
            sql.append(
                f"ALTER TABLE {_q(t)} ADD COLUMN {_q(COLONNE)} INTEGER"
            )
        sql.append(
            f"UPDATE {_q(t)} SET {_q(COLONNE)} = {sid} "
            f"WHERE {_q(COLONNE)} IS NULL"
        )
        # DEFAULT = sécurité : l'ancien code (déployé) continue d'écrire.
        sql.append(
            f"ALTER TABLE {_q(t)} ALTER COLUMN {_q(COLONNE)} SET DEFAULT {sid}"
        )
        if t not in TABLES_SCHOOL_ID_NULLABLE:
            sql.append(
                f"ALTER TABLE {_q(t)} ALTER COLUMN {_q(COLONNE)} SET NOT NULL"
            )

    # 2. Abandon des contraintes remplacées ----------------------------------
    #    Ordre imposé par PostgreSQL : les FK s'appuient sur les index de clé
    #    primaire ou d'unicité, il faut donc les supprimer AVANT les PK, et
    #    les supprimer toutes (toutes tables confondues) avant la première PK.
    for t in TABLES:
        for nom in sorted(avant[t]["f"]):
            sql.append(f"ALTER TABLE {_q(t)} DROP CONSTRAINT {_q(nom)}")
    #    …y compris les clés étrangères venues de tables non migrées
    #    (`membres`), sans quoi la première clé primaire retirée échouerait.
    for t, nom, _definition in a_relacher:
        sql.append(f"ALTER TABLE {_q(t)} DROP CONSTRAINT {_q(nom)}")
    for t in sorted(UNIQUES_A_REFAIRE):
        for nom in sorted(avant[t]["u"]):
            sql.append(f"ALTER TABLE {_q(t)} DROP CONSTRAINT {_q(nom)}")
    for t in TABLES:
        for nom in sorted(avant[t]["p"]):
            sql.append(f"ALTER TABLE {_q(t)} DROP CONSTRAINT {_q(nom)}")

    # 3. Reconstruction depuis les modèles (parité garantie) -----------------
    for t in TABLES:
        table = Base.metadata.tables[t]
        pk = ddl_pk(table)
        if pk:
            sql.append(pk)
    for t in TABLES:
        table = Base.metadata.tables[t]
        for fk in sorted(table.foreign_key_constraints, key=str):
            sql.append(ddl_fk(table, fk))
    for t in sorted(UNIQUES_A_REFAIRE):
        for uq in uniques_modele(Base.metadata.tables[t]):
            sql.append(ddl_unique(Base.metadata.tables[t], uq))
    #    …et enfin les clés étrangères des tables non migrées, rétablies
    #    à l'identique (elles n'ont pas à changer : elles ne portent pas
    #    de `school_id`).
    for t, nom, definition in a_relacher:
        sql.append(
            _equilibre(
                f"ALTER TABLE {_q(t)} ADD CONSTRAINT {_q(nom)} {definition}"
            )
        )

    return sql


def verifier_apres(conn, avant: dict[str, int]) -> list[str]:
    """Contrôle final : comptages, school_id, parité de schéma. Renvoie les écarts.

    Toutes les lectures sont groupées — trois requêtes pour l'ensemble du
    contrôle, au lieu d'une centaine (latence de la base hébergée).
    """
    ecarts: list[str] = []
    # Les relevés mémorisés datent d'avant la bascule : ils ne sont plus valides.
    _RELEVES.pop("contraintes_colonnes", None)
    _RELEVES.pop("colonnes", None)

    apres = compter_plusieurs(conn, sorted(avant))
    for t, n in avant.items():
        if apres.get(t) != n:
            ecarts.append(f"{t} : {n} lignes avant, {apres.get(t)} après")

    for t, nuls in lignes_sans_school_id(
        conn, [x for x in TABLES if x not in TABLES_SCHOOL_ID_NULLABLE]
    ).items():
        if nuls:
            ecarts.append(f"{t} : {nuls} ligne(s) sans school_id")

    # Parité PK / FK / UNIQUE avec les modèles, relevée dans le catalogue.
    releves = contraintes_du_schema(conn)
    pk: dict[str, tuple] = {}
    uniques: dict[str, set] = {}
    fks: dict[str, set] = {}
    for (table, _nom), (type_, cols, table_ref, cols_ref) in releves.items():
        if type_ == "p":
            pk[table] = tuple(sorted(cols))
        elif type_ == "u":
            uniques.setdefault(table, set()).add(tuple(sorted(cols)))
        elif type_ == "f":
            fks.setdefault(table, set()).add(
                (tuple(sorted(cols)), table_ref, tuple(sorted(cols_ref)))
            )

    for t in TABLES:
        table = Base.metadata.tables[t]
        pk_modele = tuple(sorted(c.name for c in table.primary_key.columns))
        if pk_modele != pk.get(t):
            ecarts.append(f"{t} : PK {pk.get(t)} ≠ modèle {pk_modele}")

        fk_modele = {
            (tuple(sorted(e.parent.name for e in fk.elements)),
             list(fk.elements)[0].column.table.name,
             tuple(sorted(e.column.name for e in fk.elements)))
            for fk in table.foreign_key_constraints
        }
        fk_base = fks.get(t, set())
        if fk_modele != fk_base:
            ecarts.append(
                f"{t} : FK manquantes {sorted(fk_modele - fk_base)} / "
                f"inattendues {sorted(fk_base - fk_modele)}"
            )

    for t in sorted(UNIQUES_A_REFAIRE):
        uq_modele = {
            tuple(sorted(c.name for c in uq.columns))
            for uq in uniques_modele(Base.metadata.tables[t])
        }
        uq_base = uniques.get(t, set())
        if uq_modele != uq_base:
            ecarts.append(f"{t} : UNIQUE {sorted(uq_base)} ≠ modèle {sorted(uq_modele)}")

    return ecarts


# ------------------------------------------------------------------ Moteur ----
def main() -> None:
    _preparer_sortie()

    url_brute = (settings.database_url or "").strip()
    if not url_brute:
        _echec(
            "DATABASE_URL n'est pas définie. Ce script ne migre que PostgreSQL :\n"
            "        set DATABASE_URL=postgresql://user:mdp@hote:5432/postgres"
        )
    if make_url(url_brute).get_backend_name() != "postgresql":
        _echec("DATABASE_URL ne pointe pas vers PostgreSQL.")

    appliquer = "--appliquer" in sys.argv
    moteur = create_engine(settings.engine_url, pool_pre_ping=True)
    url = make_url(settings.engine_url)

    print("=" * 72)
    print("Migration Phase 2 + 3 — isolation multi-établissements")
    print(f"Cible : {url.host}/{url.database} (utilisateur {url.username})")
    print("Mode  :", "EXÉCUTION RÉELLE (--appliquer)" if appliquer else "simulation (aucune écriture)")
    print("=" * 72)

    with moteur.connect() as conn:
        presentes = set(tables_du_schema(conn))
        cibles = [t for t in TABLES if t in presentes]
        sid = controles_avant(conn, cibles)
        print(f"[i] Établissement de rattachement : école n° {sid}")
        avant = compter_plusieurs(conn, cibles)
        print("[i] Lignes avant :", ", ".join(f"{t}={n}" for t, n in avant.items()))
        sql = plan_sql(conn, sid)

    print("-" * 72)
    print(f"{len(sql)} instruction(s) préparée(s) :")
    for i, req in enumerate(sql, 1):
        print(f"  {i:3d}. {req}")
    print("-" * 72)

    if not appliquer:
        print("[--] Simulation : rien n'a été écrit.")
        print("     Pour appliquer réellement : ajoutez --appliquer")
        return

    with moteur.begin() as conn:
        for req in sql:
            if req.startswith("--"):
                continue
            conn.execute(text(req))
        # Création des tables Phase 3 (membres, membres_invitations).
        tables_nouvelles = [
            Base.metadata.tables[t]
            for t in TABLES_NOUVELLES
            if t in Base.metadata.tables
        ]
        Base.metadata.create_all(bind=conn, tables=tables_nouvelles)

        ecarts = verifier_apres(conn, avant)
        if ecarts:
            raise RuntimeError(
                "Contrôle final en échec, transaction annulée :\n  - "
                + "\n  - ".join(ecarts)
            )

    # --- Relecture hors transaction (résultat définitif) --------------------
    oublier_releves()  # le schéma vient de changer : aucun relevé n'est valide
    with moteur.connect() as conn:
        ecarts = verifier_apres(conn, avant)
        apres = compter_plusieurs(conn, cibles)
        print("[OK] Lignes après :", ", ".join(
            f"{t}={apres.get(t)}" for t in cibles
        ))
    if ecarts:
        _echec("écarts constatés après validation : " + " ; ".join(ecarts))

    print("=" * 72)
    print("[OK] Migration terminée : aucune donnée perdue, schéma conforme aux modèles.")
    print("     Pensez à déployer immédiatement le nouveau code (Phase 2 + 3),")
    print("     puis à créer la sauvegarde Supabase du nouvel état.")
    print("=" * 72)


if __name__ == "__main__":
    main()
