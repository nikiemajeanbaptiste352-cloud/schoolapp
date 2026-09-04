"""Routes — école & annonces (lecture publique, écriture admin)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import ROLE_ADMIN, require_roles
from app.database import get_db
from app.models import Annonce, Ecole
from app.schemas import EcoleOut, MessageOut
from app.services.sd import annonce_to_dict

router = APIRouter(prefix="/api/v1", tags=["école & annonces"])


# ---------------------------------------------------------------------------
# École
# ---------------------------------------------------------------------------
@router.get("/ecole", response_model=EcoleOut, summary="Informations de l'école")
def lire_ecole(db: Session = Depends(get_db)) -> Ecole:
    ecole = db.scalar(select(Ecole).limit(1))
    if ecole is None:
        raise HTTPException(status_code=404, detail="École non configurée.")
    return ecole


@router.put("/ecole", response_model=EcoleOut, summary="Modifier l'école (admin)")
def modifier_ecole(
    body: EcoleOut,
    db: Session = Depends(get_db),
    _admin=Depends(require_roles(ROLE_ADMIN)),
) -> Ecole:
    ecole = db.scalar(select(Ecole).limit(1))
    if ecole is None:
        raise HTTPException(status_code=404, detail="École non configurée.")
    for champ, valeur in body.model_dump().items():
        setattr(ecole, champ, valeur)
    db.commit()
    db.refresh(ecole)
    return ecole


# ---------------------------------------------------------------------------
# Annonces
# ---------------------------------------------------------------------------
@router.get("/annonces", summary="Liste des annonces")
def liste_annonces(db: Session = Depends(get_db)) -> dict:
    annonces = db.execute(select(Annonce).order_by(Annonce.date)).scalars().all()
    return {"annonces": [annonce_to_dict(a) for a in annonces]}


@router.post("/annonces", summary="Créer une annonce (admin)")
def creer_annonce(
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_roles(ROLE_ADMIN)),
) -> dict:
    # Identifiant auto : A{max+1}
    dernier = db.execute(
        select(Annonce).order_by(Annonce.id.desc()).limit(1)
    ).scalar_one_or_none()
    num = int(dernier.id[1:]) + 1 if dernier else 1
    annonce = Annonce(
        id=f"A{num}",
        titre=payload["titre"],
        contenu=payload["contenu"],
        categorie=payload.get("categorie", "Information"),
        date=date.fromisoformat(payload["date"]),
        auteur=payload.get("auteur", "Administration"),
        important=bool(payload.get("important", False)),
    )
    db.add(annonce)
    db.commit()
    db.refresh(annonce)
    return annonce_to_dict(annonce)


@router.put("/annonces/{annonce_id}", summary="Modifier une annonce (admin)")
def modifier_annonce(
    annonce_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_roles(ROLE_ADMIN)),
) -> dict:
    annonce = db.get(Annonce, annonce_id)
    if annonce is None:
        raise HTTPException(status_code=404, detail="Annonce introuvable.")
    for champ in ("titre", "contenu", "categorie", "auteur"):
        if champ in payload:
            setattr(annonce, champ, payload[champ])
    if "date" in payload:
        annonce.date = date.fromisoformat(payload["date"])
    if "important" in payload:
        annonce.important = bool(payload["important"])
    db.commit()
    db.refresh(annonce)
    return annonce_to_dict(annonce)


@router.delete("/annonces/{annonce_id}", response_model=MessageOut, summary="Supprimer une annonce (admin)")
def supprimer_annonce(
    annonce_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_roles(ROLE_ADMIN)),
) -> MessageOut:
    annonce = db.get(Annonce, annonce_id)
    if annonce is None:
        raise HTTPException(status_code=404, detail="Annonce introuvable.")
    db.delete(annonce)
    db.commit()
    return MessageOut(message="Annonce supprimée.")
