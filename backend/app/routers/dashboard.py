"""Routes — tableau de bord : agrégats globaux de l'établissement."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends

from app.database import get_db
from app.models import (
    Annonce,
    Classe,
    Eleve,
    Enseignant,
    Matiere,
    Paiement,
    Presence,
)
from app.services import sd

router = APIRouter(prefix="/api/v1", tags=["tableau de bord"])


@router.get("/dashboard", summary="Agrégats du tableau de bord")
def resume_dashboard(db: Session = Depends(get_db)) -> dict:
    # --- Compteurs généraux ---
    actifs = db.scalar(select(func.count(Eleve.id)).where(Eleve.statut == "Actif")) or 0
    enseignants = db.scalar(select(func.count(Enseignant.id))) or 0
    classes_nb = db.scalar(select(func.count(Classe.id))) or 0

    # --- Effectifs par classe ---
    lignes = db.execute(
        select(Eleve.classe_id, func.count(Eleve.id))
        .group_by(Eleve.classe_id)
    ).all()
    effectifs = {cid: nb for cid, nb in lignes}
    par_classe = []
    for cls_id in sd.CLASSES_ORDER:
        cls = db.get(Classe, cls_id)
        if cls:
            par_classe.append({
                "id": cls.id, "nom": cls.nom, "cycle": cls.cycle,
                "effectif": effectifs.get(cls.id, 0),
            })

    # --- Présence globale (taux moyen sur les 12 semaines) ---
    presences = db.execute(select(Presence)).scalars().all()
    taux_presence = 100
    if presences:
        absents = sum(1 for p in presences if p.statut == "A")
        taux_presence = round((len(presences) - absents) / len(presences) * 100)

    # --- Répartition des statuts de paiement ---
    paiements = db.execute(select(Paiement)).scalars().all()
    statuts = {"Payé": 0, "Partiellement payé": 0, "Impayé": 0}
    for p in paiements:
        s = sd.statut_paiement(p)
        statuts[s] = statuts.get(s, 0) + 1

    # --- Moyenne générale de l'établissement ---
    eleves = db.execute(select(Eleve)).scalars().all()
    moyennes = [sd.moyennes_eleve(db, e.id)["generale"] for e in eleves]
    moyenne_etab = round(sum(moyennes) / len(moyennes), 2) if moyennes else 0

    annonces = db.execute(select(Annonce).order_by(Annonce.date.desc()).limit(3)).scalars().all()

    return {
        "compteurs": {
            "elevesActifs": actifs,
            "enseignants": enseignants,
            "classes": classes_nb,
            "matieres": db.scalar(select(func.count(Matiere.id))) or 0,
        },
        "tauxPresence": taux_presence,
        "moyenneGenerale": moyenne_etab,
        "effectifsParClasse": par_classe,
        "paiements": {**statuts, "total": len(paiements)},
        "annonces": [sd.annonce_to_dict(a) for a in annonces],
    }
