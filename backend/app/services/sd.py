"""Services de parité — reproduisent fidèlement les calculs de `js/data.js`.

Chaque fonction renvoie des dictionnaires "prêts JSON" dont les clés
correspondent exactement à celles attendues par le front (window.SD),
pour une bascule d'intégration sans régression.
"""

from __future__ import annotations

import math
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Classe,
    Eleve,
    Enseignant,
    Matiere,
    Note,
    Paiement,
    Presence,
    classe_matiere,
)

# ---------------------------------------------------------------------------
# Ordres de référence (miroir des tableaux de data.js — pour la stabilité)
# ---------------------------------------------------------------------------
CLASSES_ORDER = ["6A", "6B", "5A", "5B", "4A", "3A", "3B", "2A", "1A", "TA"]
MATIERES_ORDER = ["S1", "S2", "S3", "S4", "S5", "S6", "S7"]
MATIERES_LYCEE = ["S1", "S2", "S3", "S4", "S5", "S6", "S8", "S7"]

EVALS = ["Devoir 1", "Devoir 2", "Composition"]
JOURS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi"]
CRENEAUX = [
    {"label": "07h30 – 09h00", "pause": False},
    {"label": "09h00 – 10h30", "pause": False},
    {"label": "10h45 – 12h15", "pause": True},  # mercredi & samedi : créneau 3 vide
    {"label": "15h00 – 16h30", "pause": False},
]
LIB_PRESENCE = {"P": "Présent", "R": "Retard", "A": "Absent"}


def _arrondi2(x: float) -> float:
    """Math.round(x*100)/100 — arrondi demi-vers-le-haut à 2 décimales."""
    return math.floor(x * 100 + 0.5) / 100


# ---------------------------------------------------------------------------
# Consultations courantes
# ---------------------------------------------------------------------------
def get_classe(db: Session, classe_id: str) -> Classe | None:
    return db.get(Classe, classe_id)


def get_matiere(db: Session, matiere_id: str) -> Matiere | None:
    return db.get(Matiere, matiere_id)


def get_eleve(db: Session, eleve_id: str) -> Eleve | None:
    return db.get(Eleve, eleve_id)


def get_enseignant(db: Session, enseignant_id: str) -> Enseignant | None:
    return db.get(Enseignant, enseignant_id)


def matieres_ids_classe(db: Session, classe_id: str) -> list[str]:
    """Ids ordonnés des matières d'une classe (classe_matiere.ordre)."""
    cls = get_classe(db, classe_id)
    if cls is None:
        return []
    rows = db.execute(
        select(classe_matiere.c.matiere_id)
        .where(classe_matiere.c.classe_id == classe_id)
        .order_by(classe_matiere.c.ordre)
    ).all()
    ids = [r[0] for r in rows]
    # Filet de sécurité si le programme n'a pas été inséré
    return ids or (MATIERES_LYCEE if cls.cycle == "Lycée" else MATIERES_ORDER)


def matieres_de_classe(db: Session, classe_id: str) -> list[dict]:
    """Liste des matières d'une classe (objet complet) — ordre du front."""
    mat = {m.id: m for m in db.execute(select(Matiere)).scalars()}
    return [mat[i] for i in matieres_ids_classe(db, classe_id) if i in mat]


def eleves_de_classe(db: Session, classe_id: str) -> list[Eleve]:
    """Élèves d'une classe triés comme le front (nom+prenom, collation fr)."""
    eleves = db.execute(
        select(Eleve).where(Eleve.classe_id == classe_id)
    ).scalars().all()
    return sorted(
        eleves,
        key=lambda e: (e.nom + " " + e.prenom).casefold(),
    )


# ---------------------------------------------------------------------------
# Notes / moyennes / classements (parité stricte avec data.js)
# ---------------------------------------------------------------------------
def notes_eleve(db: Session, eleve_id: str, matiere_id: str | None = None) -> list[Note]:
    stmt = select(Note).where(Note.eleve_id == eleve_id)
    if matiere_id:
        stmt = stmt.where(Note.matiere_id == matiere_id)
    return list(db.execute(stmt).scalars())


def moyennes_eleve(db: Session, eleve_id: str) -> dict:
    """Retourne {parMatiere, generale, totalCoef} — mêmes clés que SD."""
    eleve = get_eleve(db, eleve_id)
    if eleve is None:
        return {"parMatiere": [], "generale": 0, "totalCoef": 0}

    notes = db.execute(
        select(Note).where(Note.eleve_id == eleve_id)
    ).scalars().all()
    par_matiere: list[dict] = []
    for m in matieres_de_classe(db, eleve.classe_id):
        vals = [n.note for n in notes if n.matiere_id == m.id]
        if not vals:
            continue
        moy = sum(vals) / len(vals)
        par_matiere.append({
            "matiereId": m.id,
            "matiere": m.nom,
            "icone": m.icone,
            "coef": m.coef,
            "moyenne": _arrondi2(moy),
        })
    num = sum(p["moyenne"] * p["coef"] for p in par_matiere)
    coefs = sum(p["coef"] for p in par_matiere)
    generale = num / coefs if coefs else 0.0
    return {
        "parMatiere": par_matiere,
        "generale": _arrondi2(generale),
        "totalCoef": coefs,
    }


def rang_eleve(db: Session, eleve_id: str) -> dict | None:
    """Classement de l'élève dans sa classe → {rang, total} (ou None)."""
    eleve = get_eleve(db, eleve_id)
    if eleve is None:
        return None
    camarades = [
        {"id": e.id, "moyenne": moyennes_eleve(db, e.id)["generale"]}
        for e in eleves_de_classe(db, eleve.classe_id)
    ]
    # tri desc stable (mêmes égalités que le front)
    camarades.sort(key=lambda c: c["moyenne"], reverse=True)
    for i, c in enumerate(camarades):
        if c["id"] == eleve_id:
            return {"rang": i + 1, "total": len(camarades)}
    return None


def appreciation(moyenne: float) -> dict:
    """Appréciation + mention — seuils identiques au front."""
    if moyenne >= 16:
        return {"texte": "Excellent travail, félicitations ! Continuez ainsi.", "mention": "Excellent"}
    if moyenne >= 14:
        return {"texte": "Très bon travail. Gardez ce niveau d'exigence.", "mention": "Très bien"}
    if moyenne >= 12:
        return {"texte": "Bon travail. Quelques efforts supplémentaires vous mèneront très loin.", "mention": "Bien"}
    if moyenne >= 10:
        return {"texte": "Travail passable. Des efforts restent à fournir dans certaines matières.", "mention": "Assez bien"}
    if moyenne >= 8:
        return {"texte": "Résultats insuffisants, un sursaut d'effort est nécessaire.", "mention": "Insuffisant"}
    return {"texte": "Résultats très faibles. Un accompagnement régulier est indispensable.", "mention": "Très insuffisant"}


# ---------------------------------------------------------------------------
# Présences
# ---------------------------------------------------------------------------
def taux_presence(db: Session, eleve_id: str) -> int:
    arr = db.execute(
        select(Presence).where(Presence.eleve_id == eleve_id)
    ).scalars().all()
    if not arr:
        return 100
    absents = sum(1 for p in arr if p.statut == "A")
    return math.floor(((len(arr) - absents) / len(arr)) * 100 + 0.5)


# ---------------------------------------------------------------------------
# Paiements
# ---------------------------------------------------------------------------
def montant_paye(paiement: Paiement) -> int:
    return sum(v.montant for v in paiement.versements)


def statut_paiement(paiement: Paiement) -> str:
    paye = montant_paye(paiement)
    if paye >= paiement.total:
        return "Payé"
    if paye <= 0:
        return "Impayé"
    return "Partiellement payé"


def paiement_eleve(db: Session, eleve_id: str) -> Paiement | None:
    return db.scalar(select(Paiement).where(Paiement.eleve_id == eleve_id))


# ---------------------------------------------------------------------------
# Emploi du temps (parité stricte : même grille que le front)
# ---------------------------------------------------------------------------
def emploi_du_temps(db: Session, classe_id: str) -> list[dict]:
    cls = get_classe(db, classe_id)
    if cls is None:
        return []
    ids = matieres_ids_classe(db, classe_id)
    shift = CLASSES_ORDER.index(classe_id) if classe_id in CLASSES_ORDER else 0

    matieres = {m.id: m for m in db.execute(select(Matiere)).scalars()}
    enseignants = list(db.execute(select(Enseignant)).scalars())

    grid: list[dict] = []
    for j, jour in enumerate(JOURS):
        for ci, creneau in enumerate(CRENEAUX):
            # Créneau 3 (10h45) vide le mercredi (j=2) et le samedi (j=5)
            if ci == 2 and j in (2, 5):
                continue
            idx = (j + ci + shift) % len(ids)
            mid = ids[idx]
            mat = matieres.get(mid)
            prof = next((e for e in enseignants if e.matiere_id == mid), None)
            grid.append({
                "classe": classe_id,
                "jour": jour,
                "creneau": ci,
                "heure": creneau["label"],
                "matiere": mat.nom if mat else "Étude",
                "matiereId": mid,
                "enseignant": f"{prof.nom} {prof.prenom}" if prof else "—",
                "salle": f"{cls.salle} / {ci + 1}",
            })
    return grid


# ---------------------------------------------------------------------------
# Sérialisation des entités (clés compatibles front)
# ---------------------------------------------------------------------------
def eleve_to_dict(eleve: Eleve) -> dict:
    data: dict[str, Any] = {
        "id": eleve.id,
        "nom": eleve.nom,
        "prenom": eleve.prenom,
        "sexe": eleve.sexe,
        "naissance": eleve.naissance.isoformat(),
        "classe": eleve.classe_id,
        "statut": eleve.statut,
        "inscription": eleve.inscription.isoformat(),
        "parent": parent_to_dict(eleve.parent) if eleve.parent else None,
    }
    return data


def parent_to_dict(parent) -> dict | None:
    if parent is None:
        return None
    return {
        "id": parent.id,
        "nom": parent.nom,
        "lien": parent.lien,
        "tel": parent.tel,
        "email": parent.email,
        "profession": parent.profession,
        "adresse": parent.adresse,
    }


def classe_to_dict(db: Session, classe: Classe, effectif: bool = True) -> dict:
    data = {
        "id": classe.id,
        "nom": classe.nom,
        "cycle": classe.cycle,
        "salle": classe.salle,
        "principal": classe.principal_id,
    }
    if effectif:
        nb = db.scalar(select(func.count(Eleve.id)).where(Eleve.classe_id == classe.id)) or 0
        data["effectif"] = nb
    return data


def matiere_to_dict(matiere: Matiere) -> dict:
    return {
        "id": matiere.id,
        "nom": matiere.nom,
        "coef": matiere.coef,
        "icone": matiere.icone,
        "couleur": matiere.couleur,
    }


def enseignant_to_dict(enseignant: Enseignant) -> dict:
    mat = enseignant.matiere
    return {
        "id": enseignant.id,
        "nom": enseignant.nom,
        "prenom": enseignant.prenom,
        "sexe": enseignant.sexe,
        "tel": enseignant.tel,
        "email": enseignant.email,
        "matiere": enseignant.matiere_id,
        "matiereNom": mat.nom if mat else "—",
        "classes": [c.id for c in enseignant.classes],
        "statut": enseignant.statut,
    }


def annonce_to_dict(annonce) -> dict:
    return {
        "id": annonce.id,
        "titre": annonce.titre,
        "contenu": annonce.contenu,
        "categorie": annonce.categorie,
        "date": annonce.date.isoformat(),
        "auteur": annonce.auteur,
        "important": bool(annonce.important),
    }
