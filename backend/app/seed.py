"""Seed — deux modes.

- `seed_all` + `seed_users` : jeu de démonstration (données fictives), utilisé
  uniquement quand `seed_demo=True` (tests pytest, vitrine). L'algorithme
  déterministe (notes, présences, paiements, parents) est porté depuis le
  JavaScript d'origine pour garantir la parité bulletins / classements.

- `seed_bootstrap` : mode « données réelles » (défaut au démarrage) — la base
  démarre **vide**, sans aucune donnée fictive ; seul le compte administrateur
  initial est créé s'il n'existe encore aucun utilisateur.
"""

from __future__ import annotations

import math
import re
import unicodedata
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import SessionLocal, init_db
from app.models import (
    Annonce,
    Classe,
    Ecole,
    Eleve,
    Enseignant,
    Matiere,
    Note,
    Paiement,
    Parent,
    Presence,
    User,
    Versement,
    classe_matiere,
    enseignant_classe,
)

# ---------------------------------------------------------------
# Référentiels constants (miroir de window.SD)
# ---------------------------------------------------------------
ECOLES = {
    "nom": "Complexe Scolaire Privé Le Savoir",
    "sigle": "CSP Le Savoir",
    "slogan": "Éduquer, former, réussir",
    "annee": "2026 – 2027",
    "devise": "FCFA",
    "telephone": "+226 25 40 12 34",
    "email": "contact@lesavoir.edu",
    "adresse": "Avenue de la Liberté, Ouagadougou — Burkina Faso",
    "version": "1.0.0",
}

EVALS = ["Devoir 1", "Devoir 2", "Composition"]
JOURS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi"]
CRENEAUX = [
    {"label": "07h30 – 09h00", "pause": False},
    {"label": "09h00 – 10h30", "pause": False},
    {"label": "10h45 – 12h15", "pause": True},
    {"label": "15h00 – 16h30", "pause": False},
]
# Programme Collège : S1..S7 ; Lycée : Philosophie (S8) avant EPS (S7)
PROGRAMME_COLLEGE = ["S1", "S2", "S3", "S4", "S5", "S6", "S7"]
PROGRAMME_LYCEE = ["S1", "S2", "S3", "S4", "S5", "S6", "S8", "S7"]

MONTANTS = [60000, 50000, 40000]
DATES_PAIEMENT = ["2026-10-05", "2026-11-02", "2026-12-01"]
MODES = ["Espèces", "Mobile Money", "Chèque"]

PRENOMS_PARENTS = [
    "Moussa", "Aïssata", "Boureima", "Mariam", "Issouf", "Rasmata",
    "Seydou", "Fatoumata", "Adama", "Hawa", "Idrissa", "Kadidia",
    "Oumar", "Salimata", "Bakary",
]
PROFESSIONS = [
    "Commerçant", "Enseignant", "Fonctionnaire", "Agriculteur", "Infirmier",
    "Technicien", "Commerçante", "Menuisier", "Secrétaire", "Transporteur",
]
QUARTIERS = ["Ouaga 2000", "Tampouy", "Karpala", "Dassasgho", "Pissy", "Gounghin"]


# ---------------------------------------------------------------
# Outils — portage exact du générateur déterministe JS
# ---------------------------------------------------------------
def rand(n: int) -> float:
    """Équivalent de (Math.sin(n) * 10000) - Math.floor(...) en JS."""
    x = math.sin(n) * 10000.0
    return x - math.floor(x)


def js_round(x: float) -> float:
    """Math.round JS (demi-arrondi vers +inf), ≠ round Python."""
    return math.floor(x + 0.5)


def norm_email(prenom: str, nom: str) -> str:
    """Réplique de .normalize('NFD').replace(/[\u0300-\u036f]/g, '') en JS."""
    s = unicodedata.normalize("NFD", f"{prenom}.{nom}".lower())
    return re.sub(r"[\u0300-\u036f]", "", s)


# ---------------------------------------------------------------
# Données statiques (copie exacte de data.js)
# ---------------------------------------------------------------
CLASSES = [
    ("6A", "6e A", "Collège", "C-101", "T002"),
    ("6B", "6e B", "Collège", "C-102", "T002"),
    ("5A", "5e A", "Collège", "C-201", "T004"),
    ("5B", "5e B", "Collège", "C-202", "T004"),
    ("4A", "4e A", "Collège", "C-203", "T003"),
    ("3A", "3e A", "Collège", "C-204", "T001"),
    ("3B", "3e B", "Collège", "C-205", "T005"),
    ("2A", "2nde A", "Lycée", "L-101", "T006"),
    ("1A", "1ère A", "Lycée", "L-102", "T006"),
    ("TA", "Terminale A", "Lycée", "L-201", "T005"),
]

MATIERES = [
    ("S1", "Mathématiques", 4, "🧮", "blue"),
    ("S2", "Français", 4, "📖", "green"),
    ("S3", "Anglais", 2, "🌍", "cyan"),
    ("S4", "SVT", 2, "🔬", "green"),
    ("S5", "Histoire-Géographie", 2, "🗺️", "orange"),
    ("S6", "Physique-Chimie", 3, "⚗️", "purple"),
    ("S7", "EPS", 1, "🏃", "red"),
    ("S8", "Philosophie", 2, "💭", "purple"),
]

ENSEIGNANTS = [
    ("T001", "Ouédraogo", "Jean", "M", "70 11 22 33", "j.ouedraogo@lesavoir.edu", "S1", ["3A", "3B"]),
    ("T002", "Kaboré", "Salimata", "F", "70 44 55 66", "s.kabore@lesavoir.edu", "S2", ["6A", "6B", "5A", "5B", "4A"]),
    ("T003", "Zongo", "Adama", "M", "71 23 45 67", "a.zongo@lesavoir.edu", "S3", ["3A", "3B", "4A", "2A"]),
    ("T004", "Sawadogo", "Martine", "F", "70 98 76 54", "m.sawadogo@lesavoir.edu", "S4", ["3A", "3B", "5A", "5B"]),
    ("T005", "Traoré", "Boureima", "M", "72 12 34 56", "b.traore@lesavoir.edu", "S6", ["3A", "3B", "2A", "1A", "TA"]),
    ("T006", "Diallo", "Awa", "F", "71 66 77 88", "a.diallo@lesavoir.edu", "S5", ["2A", "1A", "TA", "4A"]),
    ("T007", "Ouattara", "Lassina", "M", "73 45 67 89", "l.ouattara@lesavoir.edu", "S7", ["6A", "6B", "5A", "5B", "4A", "3A", "3B", "2A", "1A", "TA"]),
]

# [id, nom, prenom, sexe, naissance, classe, statut]
ELEVES_BRUTS = [
    ["EL001", "Kaboré", "Paul", "M", "2009-04-12", "3A", "Actif"],
    ["EL002", "Ouédraogo", "Marie", "F", "2010-01-25", "4A", "Actif"],
    ["EL003", "Sawadogo", "Jean", "M", "2009-11-03", "3A", "Actif"],
    ["EL004", "Zongo", "Awa", "F", "2011-07-19", "5A", "Actif"],
    ["EL005", "Traoré", "Issa", "M", "2012-02-08", "6A", "Actif"],
    ["EL006", "Ouattara", "Fatou", "F", "2009-09-30", "3A", "Actif"],
    ["EL007", "Diallo", "Moussa", "M", "2010-05-14", "4A", "Inactif"],
    ["EL008", "Compaoré", "Aïcha", "F", "2008-03-22", "2A", "Actif"],
    ["EL009", "Ilboudo", "Abdoulaye", "M", "2007-12-01", "1A", "Actif"],
    ["EL010", "Nikiéma", "Salif", "M", "2010-08-17", "3B", "Actif"],
    ["EL011", "Bationo", "Prisca", "F", "2012-06-05", "6B", "Actif"],
    ["EL012", "Kafando", "Rachid", "M", "2010-03-11", "5B", "Actif"],
    ["EL013", "Rouamba", "Grâce", "F", "2006-04-17", "TA", "Actif"],
    ["EL014", "Sanou", "Alima", "F", "2009-06-23", "3A", "Actif"],
    ["EL015", "Dabiré", "Éric", "M", "2009-01-30", "3A", "Actif"],
]

ANNONCES = [
    {
        "titre": "Rentrée scolaire 2026-2027",
        "contenu": "La rentrée scolaire aura lieu le lundi 5 octobre 2026 à 07h30 précises. "
                   "Les élèves sont priés de venir avec leurs fournitures et leurs tenues complètes. "
                   "Les parents sont attendus pour une rencontre d'information à 09h00.",
        "categorie": "Information", "date": "2026-09-05", "auteur": "Administration", "important": True,
    },
    {
        "titre": "Réunion des parents d'élèves",
        "contenu": "Une réunion générale des parents d'élèves se tiendra le samedi 19 septembre 2026 dans "
                   "la cour de l'école. Ordre du jour : résultats de l'année écoulée, règlement intérieur "
                   "et projets de l'établissement pour cette nouvelle année.",
        "categorie": "Réunion", "date": "2026-09-12", "auteur": "Comité de gestion", "important": False,
    },
    {
        "titre": "Concours général de mathématiques",
        "contenu": "Les élèves de 3e et de Terminale désireux de participer au concours général de "
                   "mathématiques doivent s'inscrire auprès de M. Ouédraogo Jean avant le 30 septembre. "
                   "Les épreuves se dérouleront en novembre.",
        "categorie": "Concours", "date": "2026-09-18", "auteur": "Cellule pédagogique", "important": False,
    },
    {
        "titre": "Rappel — Paiement des frais scolaires",
        "contenu": "Nous rappelons aux parents que le paiement des frais de scolarité peut être effectué au "
                   "secrétariat ou par Mobile Money. Un reçu vous sera remis pour chaque versement. Les élèves "
                   "dont les frais ne sont pas soldés ne pourront pas composer aux examens.",
        "categorie": "Finance", "date": "2026-11-10", "auteur": "Service financier", "important": True,
    },
]


# ---------------------------------------------------------------
# Seed principal (idempotent)
# ---------------------------------------------------------------
def _deja_peuple(db: Session) -> bool:
    return db.execute(select(Ecole)).first() is not None


def seed_all(db: Session) -> bool:
    """Insère les données de démonstration si la base est vide. Retourne True si seed exécuté."""
    if _deja_peuple(db):
        return False

    # --- École ---
    db.add(Ecole(**ECOLES, id=1))

    # --- Classes & matières ---
    classes = {}
    for cid, nom, cycle, salle, principal in CLASSES:
        c = Classe(id=cid, nom=nom, cycle=cycle, salle=salle, principal_id=principal)
        db.add(c)
        classes[cid] = c

    matieres = {}
    for mid, nom, coef, icone, couleur in MATIERES:
        m = Matiere(id=mid, nom=nom, coef=coef, icone=icone, couleur=couleur)
        db.add(m)
        matieres[mid] = m

    # Programmes par classe (ordre d'affichage = ordre du front)
    for cid, _, cycle, _, _ in CLASSES:
        programme = PROGRAMME_LYCEE if cycle == "Lycée" else PROGRAMME_COLLEGE
        for ordre, mid in enumerate(programme):
            db.execute(classe_matiere.insert().values(classe_id=cid, matiere_id=mid, ordre=ordre))

    # --- Enseignants ---
    enseignants = {}
    for eid, nom, prenom, sexe, tel, email, mat, clses in ENSEIGNANTS:
        e = Enseignant(
            id=eid, nom=nom, prenom=prenom, sexe=sexe, tel=tel,
            email=email, matiere_id=mat, statut="Actif",
        )
        db.add(e)
        enseignants[eid] = e
        for cid in clses:
            db.execute(enseignant_classe.insert().values(enseignant_id=eid, classe_id=cid))

    # --- Élèves + parents ---
    for i, row in enumerate(ELEVES_BRUTS):
        eid, nom, prenom, sexe, naissance, cid, statut = row
        n = int(eid.replace("EL", ""))

        # Parent généré (portage exact de data.js)
        prenom_parent = PRENOMS_PARENTS[(n - 1) % len(PRENOMS_PARENTS)]
        tel_parent = (
            f"70 {10 + (n * 3) % 40:02d} {11 + (n * 7) % 40:02d} {22 + (n * 5) % 40:02d}"
        )
        parent = Parent(
            nom=f"{prenom_parent} {nom}",
            lien="Père" if i % 2 == 0 else "Mère",
            tel=tel_parent,
            email=f"{norm_email(prenom, nom)}@mail.com",
            profession=PROFESSIONS[n % len(PROFESSIONS)],
            adresse=QUARTIERS[n % len(QUARTIERS)],
        )
        db.add(parent)
        db.flush()  # obtient parent.id

        inscription = date(2020, 9, 10 + (i % 9))
        db.add(Eleve(
            id=eid, nom=nom, prenom=prenom, sexe=sexe,
            naissance=date.fromisoformat(naissance),
            classe_id=cid, statut=statut, inscription=inscription,
            parent_id=parent.id,
        ))

    db.flush()

    # --- Notes (déterministe, portage de data.js) ---
    for row in ELEVES_BRUTS:
        eid = row[0]
        n = int(eid.replace("EL", ""))
        cls = next(c for c in CLASSES if c[0] == row[5])
        programme = PROGRAMME_LYCEE if cls[2] == "Lycée" else PROGRAMME_COLLEGE
        for mat_id in programme:
            mat_n = int(mat_id.replace("S", ""))
            for ei in range(len(EVALS)):
                seed_n = n * 100 + mat_n * 10 + ei
                r = rand(seed_n)
                base = 9 + (n % 6)  # 9 à 14
                note = max(4, min(19.5, js_round((base + r * 5) * 2) / 2))
                db.add(Note(
                    eleve_id=eid, matiere_id=mat_id,
                    eval=EVALS[ei], note=note,
                ))

    # --- Présences (12 semaines, portage de data.js) ---
    debut = date(2026, 9, 7)  # lundi 7 septembre 2026
    for i, row in enumerate(ELEVES_BRUTS):
        for s in range(12):
            if i % 12 == s:
                statut = "A"
            elif (i * 5) % 12 == s:
                statut = "R"
            else:
                statut = "P"
            db.add(Presence(
                eleve_id=row[0], date=debut + timedelta(weeks=s), statut=statut,
            ))

    # --- Paiements + versements (portage de data.js) ---
    for row in ELEVES_BRUTS:
        eid = row[0]
        n = int(eid.replace("EL", ""))
        cls = next(c for c in CLASSES if c[0] == row[5])
        total = 200000 if cls[2] == "Lycée" else 150000
        regime = n % 4
        pai = Paiement(
            eleve_id=eid,
            motif=f"Frais de scolarité {ECOLES['annee']}",
            total=total,
        )
        db.add(pai)
        db.flush()
        nb_versements = {0: 3, 1: 2, 2: 1, 3: 0}[regime]
        for j in range(nb_versements):
            db.add(Versement(
                paiement_id=pai.id,
                montant=MONTANTS[j],
                date=date.fromisoformat(DATES_PAIEMENT[j]),
                mode=MODES[j],
            ))

    # --- Annonces ---
    for i, a in enumerate(ANNONCES, start=1):
        db.add(Annonce(
            id=f"A{i}", titre=a["titre"], contenu=a["contenu"],
            categorie=a["categorie"], date=date.fromisoformat(a["date"]),
            auteur=a["auteur"], important=a["important"],
        ))

    db.commit()
    return True


# ---------------------------------------------------------------
# Comptes utilisateurs de démonstration (Phase 2 — auth)
# ---------------------------------------------------------------
# Mot de passe unique commun à tous les comptes de démo (documenté).
PASSWORD_DEMO = "Savoir2026!"


def _nouvel_user(
    db: Session, email: str, role: str, nom: str,
    eleve_id: str | None = None,
    enseignant_id: str | None = None,
    parent_id: int | None = None,
) -> User:
    from app.security import hash_password  # import local (PyJWT déjà chargé)

    user = User(
        email=email.lower().strip(),
        password_hash=hash_password(PASSWORD_DEMO),
        role=role,
        nom=nom,
        actif=True,
        eleve_id=eleve_id,
        enseignant_id=enseignant_id,
        parent_id=parent_id,
    )
    db.add(user)
    return user


def seed_users(db: Session) -> bool:
    """Crée les comptes du jeu de démonstration (1 admin + 7 profs + 15 élèves + 15 parents).

    Idempotent : ne fait rien si des utilisateurs existent déjà.
    Mot de passe commun : {PASSWORD_DEMO}
    """
    if db.query(User).count() > 0:
        return False

    # 1. Administrateur
    _nouvel_user(db, "admin@lesavoir.edu", "Administrateur", "Administration")

    # 2. Professeurs (liés à leur fiche enseignant)
    for eid, nom, prenom, _sexe, _tel, email, _mat, _clses in ENSEIGNANTS:
        _nouvel_user(db, email, "Professeur", f"{prenom} {nom}", enseignant_id=eid)

    # 3. Élèves (liés à leur fiche élève) — email : prenom.nom@lesavoir.edu
    for row in ELEVES_BRUTS:
        eid, nom, prenom = row[0], row[1], row[2]
        _nouvel_user(
            db, f"{norm_email(prenom, nom)}@lesavoir.edu", "Élève",
            f"{prenom} {nom}", eleve_id=eid,
        )

    # 4. Parents (liés à la fiche parent du premier enfant trouvé)
    for row in ELEVES_BRUTS:
        eleve = db.get(Eleve, row[0])
        if eleve is None or eleve.parent is None:
            continue
        _nouvel_user(
            db, eleve.parent.email, "Parent",
            eleve.parent.nom, parent_id=eleve.parent.id,
        )

    db.commit()
    return True


def seed_bootstrap(db: Session) -> bool:
    """Mode données réelles : crée UNIQUEMENT le compte administrateur initial.

    Idempotent : ne fait rien si un utilisateur existe déjà. En cas de course
    entre instances serverless (déploiement Vercel), l'insertion en double est
    absorbée silencieusement (contrainte d'unicité e-mail).
    Aucune donnée fictive (élèves, classes, notes…) n'est insérée : la base
    reste vide, l'établissement est ensuite configuré par ses propres données.
    Mot de passe initial : {PASSWORD_DEMO}
    """
    if db.query(User).count() > 0:
        return False

    _nouvel_user(db, "admin@lesavoir.edu", "Administrateur", "Administration")
    try:
        db.commit()
        return True
    except IntegrityError:
        # Un autre processus a créé l'administrateur entre-temps.
        db.rollback()
        return False


# ---------------------------------------------------------------
# Point d'entrée CLI : python -m app.seed  (reset + seed de démo)
# ---------------------------------------------------------------
def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        ok_domain = seed_all(db)
        ok_users = seed_users(db)
        print("[OK] Base initialisee." if ok_domain else "[--] Donnees deja presentes (aucun changement).")
        print("[OK] Comptes crees." if ok_users else "[--] Comptes deja presents.")
        print(f"[i] Mot de passe de demonstration : {PASSWORD_DEMO}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
