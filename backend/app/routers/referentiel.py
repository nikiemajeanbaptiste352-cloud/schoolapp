"""Routes — référentiel : classes, matières, enseignants (lecture)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Classe, Enseignant, Matiere
from app.services import sd

router = APIRouter(prefix="/api/v1", tags=["référentiel"])


# ---------------------------------------------------------------------------
# Classes
# ---------------------------------------------------------------------------
@router.get("/classes", summary="Liste des classes (avec effectif)")
def liste_classes(db: Session = Depends(get_db)) -> dict:
    classes = db.execute(select(Classe)).scalars().all()
    # ordre stable identique à data.js
    par_id = {c.id: c for c in classes}
    classes_triees = [par_id[cid] for cid in sd.CLASSES_ORDER if cid in par_id]
    return {"classes": [sd.classe_to_dict(db, c) for c in classes_triees]}


@router.get("/classes/{classe_id}", summary="Détail d'une classe")
def detail_classe(classe_id: str, db: Session = Depends(get_db)) -> dict:
    cls = sd.get_classe(db, classe_id)
    if cls is None:
        raise HTTPException(status_code=404, detail="Classe introuvable.")

    principal = cls.principal
    matieres = sd.matieres_de_classe(db, classe_id)
    # Professeurs intervenant dans cette classe
    profs = db.execute(
        select(Enseignant).join(Enseignant.classes).where(Classe.id == classe_id)
    ).scalars().all()

    return {
        **sd.classe_to_dict(db, cls),
        "principalNom": f"{principal.prenom} {principal.nom}" if principal else None,
        "matieres": [sd.matiere_to_dict(m) for m in matieres],
        "enseignants": [sd.enseignant_to_dict(p) for p in profs],
        "eleves": [sd.eleve_to_dict(e) for e in sd.eleves_de_classe(db, classe_id)],
    }


@router.get("/classes/{classe_id}/emploi-du-temps", summary="Emploi du temps d'une classe")
def emploi_du_temps(classe_id: str, db: Session = Depends(get_db)) -> dict:
    cls = sd.get_classe(db, classe_id)
    if cls is None:
        raise HTTPException(status_code=404, detail="Classe introuvable.")
    return {
        "classe": sd.classe_to_dict(db, cls, effectif=False),
        "jours": sd.JOURS,
        "creneaux": sd.CRENEAUX,
        "grille": sd.emploi_du_temps(db, classe_id),
    }


# ---------------------------------------------------------------------------
# Matières
# ---------------------------------------------------------------------------
@router.get("/matieres", summary="Liste des matières")
def liste_matieres(db: Session = Depends(get_db)) -> dict:
    matieres = db.execute(select(Matiere)).scalars().all()
    par_id = {m.id: m for m in matieres}
    triees = [par_id[mid] for mid in sd.MATIERES_ORDER if mid in par_id]
    return {"matieres": [sd.matiere_to_dict(m) for m in triees]}


# ---------------------------------------------------------------------------
# Enseignants
# ---------------------------------------------------------------------------
@router.get("/enseignants", summary="Liste des enseignants")
def liste_enseignants(db: Session = Depends(get_db)) -> dict:
    ens = db.execute(select(Enseignant).order_by(Enseignant.id)).scalars().all()
    return {"enseignants": [sd.enseignant_to_dict(e) for e in ens]}


@router.get("/enseignants/{enseignant_id}", summary="Détail d'un enseignant")
def detail_enseignant(enseignant_id: str, db: Session = Depends(get_db)) -> dict:
    ens = sd.get_enseignant(db, enseignant_id)
    if ens is None:
        raise HTTPException(status_code=404, detail="Enseignant introuvable.")
    return sd.enseignant_to_dict(ens)
