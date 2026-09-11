"""Routes — tableau de bord : agrégats de l'établissement.

Les agrégats portent sur le **périmètre du compte** et non plus sur tout
l'établissement : un élève ou un parent ne voit que ses propres chiffres, et
les professeurs / surveillants n'obtiennent aucune donnée financière.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends

from app.auth import get_current_user
from app.database import get_db
from app.models import (
    Annonce,
    Classe,
    Eleve,
    Enseignant,
    Matiere,
    Paiement,
    Presence,
    User,
)
from app.services import perimetre, sd

router = APIRouter(prefix="/api/v1", tags=["tableau de bord"])


@router.get("/dashboard", summary="Agrégats du tableau de bord")
def resume_dashboard(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    sid = sd.sid_ecole(db)
    eleves = perimetre.eleves_visibles(db, user)
    ids_eleves = {e.id for e in eleves}
    complet = perimetre.ids_eleves_autorises(db, user) is None

    # --- Compteurs généraux ---
    if complet:
        actifs = db.scalar(
            select(func.count(Eleve.id)).where(
                Eleve.school_id == sid, Eleve.statut == "Actif"
            )
        ) or 0
        enseignants = db.scalar(
            select(func.count(Enseignant.id)).where(Enseignant.school_id == sid)
        ) or 0
        classes_nb = db.scalar(
            select(func.count(Classe.id)).where(Classe.school_id == sid)
        ) or 0
    else:
        actifs = sum(1 for e in eleves if e.statut == "Actif")
        enseignants = 0
        classes_nb = len({e.classe_id for e in eleves if e.classe_id})

    # --- Effectifs par classe ---
    effectifs: dict[str, int] = {}
    for eleve in eleves:
        key = eleve.classe_id or ""
        effectifs[key] = effectifs.get(key, 0) + 1
    par_classe = []
    for cls_id in sd.CLASSES_ORDER:
        cls = sd.get_classe(db, cls_id)
        if cls is None:
            continue
        nb = effectifs.get(cls.id, 0)
        if not complet and nb == 0:
            continue
        par_classe.append({
            "id": cls.id, "nom": cls.nom, "cycle": cls.cycle,
            "effectif": nb,
        })

    # --- Présences du périmètre ---
    presences: list[Presence] = []
    if complet or ids_eleves:
        stmt_presences = select(Presence).where(Presence.school_id == sid)
        if not complet:
            stmt_presences = stmt_presences.where(Presence.eleve_id.in_(ids_eleves))
        presences = list(db.execute(stmt_presences).scalars())
    taux_presence = 100
    if presences:
        absents = sum(1 for p in presences if p.statut == "A")
        taux_presence = round((len(presences) - absents) / len(presences) * 100)

    # --- Répartition des statuts de paiement (périmètre finance) ---
    ids_finance = perimetre.ids_eleves_finance(db, user)
    paiements: list[Paiement] = []
    if ids_finance != set():
        stmt_paiements = select(Paiement).where(Paiement.school_id == sid)
        if ids_finance is not None:
            stmt_paiements = stmt_paiements.where(Paiement.eleve_id.in_(ids_finance))
        paiements = list(db.execute(stmt_paiements).scalars())
    statuts = {"Payé": 0, "Partiellement payé": 0, "Impayé": 0}
    for p in paiements:
        s = sd.statut_paiement(p)
        statuts[s] = statuts.get(s, 0) + 1

    # --- Moyenne générale du périmètre ---
    moyennes = [sd.moyennes_eleve(db, e.id)["generale"] for e in eleves]
    moyenne_etab = round(sum(moyennes) / len(moyennes), 2) if moyennes else 0

    annonces = db.execute(
        select(Annonce).where(Annonce.school_id == sid)
        .order_by(Annonce.date.desc()).limit(3)
    ).scalars().all()

    return {
        "compteurs": {
            "elevesActifs": actifs,
            "enseignants": enseignants,
            "classes": classes_nb,
            "matieres": db.scalar(
                select(func.count(Matiere.id)).where(Matiere.school_id == sid)
            ) or 0,
        },
        "tauxPresence": taux_presence,
        "moyenneGenerale": moyenne_etab,
        "effectifsParClasse": par_classe,
        "paiements": {**statuts, "total": len(paiements)},
        "annonces": [sd.annonce_to_dict(a) for a in annonces],
    }
