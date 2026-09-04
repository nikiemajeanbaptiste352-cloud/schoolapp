"""Routes — présences (consultation élève/parent, pointage par classe)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import ROLE_ADMIN, ROLE_PARENT, ROLE_PROF, get_current_user, require_roles
from app.database import get_db
from app.models import Parent, Presence, User
from app.services import sd

router = APIRouter(prefix="/api/v1", tags=["présences"])


def _peut_voir_eleve(db: Session, user: User, eleve_id: str) -> bool:
    if user.role in (ROLE_ADMIN, ROLE_PROF):
        return True
    if user.role == "Élève":
        return user.eleve_id == eleve_id
    if user.role == ROLE_PARENT and user.parent_id:
        parent = db.get(Parent, user.parent_id)
        return parent is not None and any(e.id == eleve_id for e in parent.enfants)
    return False


@router.get("/eleves/{eleve_id}/presences", summary="Liste des présences d'un élève")
def presences_eleve(
    eleve_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    if not _peut_voir_eleve(db, user, eleve_id):
        raise HTTPException(status_code=403, detail="Accès refusé.")
    eleve = sd.get_eleve(db, eleve_id)
    if eleve is None:
        raise HTTPException(status_code=404, detail="Élève introuvable.")

    rows = db.execute(
        select(Presence)
        .where(Presence.eleve_id == eleve_id)
        .order_by(Presence.date)
    ).scalars().all()
    return {
        "eleveId": eleve_id,
        "taux": sd.taux_presence(db, eleve_id),
        "presences": [
            {
                "eleveId": eleve_id,
                "date": p.date.isoformat(),
                "statut": p.statut,
                "libelle": sd.LIB_PRESENCE.get(p.statut, p.statut),
            }
            for p in rows
        ],
    }


@router.post("/presences", summary="Pointer la présence d'une classe (admin/professeur)")
def pointer_presences(
    payload: dict,
    db: Session = Depends(get_db),
    _user=Depends(require_roles(ROLE_ADMIN, ROLE_PROF)),
) -> dict:
    classe = payload.get("classe")
    jour = date.fromisoformat(payload["date"])
    statuts = payload.get("statuts", {})  # {eleveId: "P"|"R"|"A"}

    if sd.get_classe(db, classe) is None:
        raise HTTPException(status_code=404, detail="Classe introuvable.")

    nb = 0
    for eleve_id, statut in statuts.items():
        if statut not in ("P", "R", "A"):
            raise HTTPException(status_code=400, detail=f"Statut invalide : {statut}")
        existant = db.scalar(
            select(Presence).where(
                Presence.eleve_id == eleve_id, Presence.date == jour
            )
        )
        if existant:
            existant.statut = statut
        else:
            db.add(Presence(eleve_id=eleve_id, date=jour, statut=statut))
        nb += 1
    db.commit()
    return {"message": f"{nb} présence(s) enregistrée(s) le {jour.isoformat()}."}
