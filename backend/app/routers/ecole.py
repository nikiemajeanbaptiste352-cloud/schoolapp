"""Routes — école & annonces (lecture réservée aux comptes de l'école,
   écriture admin)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import ROLE_ADMIN, get_current_user, require_roles
from app.database import get_db
from app.models import Annonce, Ecole, User
from app.schemas import EcoleOut, MessageOut
from app.services import sd

router = APIRouter(prefix="/api/v1", tags=["école & annonces"])


# ---------------------------------------------------------------------------
# École
# ---------------------------------------------------------------------------
@router.get("/ecole", response_model=EcoleOut, summary="Informations de l'école")
def lire_ecole(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> Ecole:
    ecole = db.scalar(select(Ecole).where(Ecole.id == sd.sid_ecole(db)).limit(1))
    if ecole is None:
        raise HTTPException(status_code=404, detail="École non configurée.")
    return ecole


@router.post("/ecole", response_model=EcoleOut, summary="Créer la fiche école (admin)")
def creer_ecole(
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_roles(ROLE_ADMIN)),
) -> Ecole:
    """Crée la fiche unique de l'établissement (permet de bootstraper une
    base vide depuis l'interface Réglages). Échoue si elle existe déjà."""
    if db.scalar(select(Ecole).limit(1)) is not None:
        raise HTTPException(status_code=409, detail="L'école est déjà configurée : utilisez la modification.")
    nom = (payload.get("nom") or "").strip()
    if not nom:
        raise HTTPException(status_code=400, detail="Le nom de l'établissement est obligatoire.")
    ecole = Ecole(
        id=1,
        nom=nom,
        sigle=payload.get("sigle") or "",
        slogan=payload.get("slogan") or "",
        annee=payload.get("annee") or "2026 – 2027",
        devise=payload.get("devise") or "FCFA",
        telephone=payload.get("telephone") or "",
        email=payload.get("email") or "",
        adresse=payload.get("adresse") or "",
        version=payload.get("version") or "1.0.0",
    )
    db.add(ecole)
    db.commit()
    db.refresh(ecole)
    return ecole


@router.put("/ecole", response_model=EcoleOut, summary="Modifier l'école (admin)")
def modifier_ecole(
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_roles(ROLE_ADMIN)),
) -> Ecole:
    ecole = db.scalar(select(Ecole).where(Ecole.id == sd.sid_ecole(db)).limit(1))
    if ecole is None:
        raise HTTPException(status_code=404, detail="École non configurée.")
    # Mise à jour partielle : seuls les champs fournis sont modifiés.
    for champ, valeur in payload.items():
        if hasattr(ecole, champ):
            setattr(ecole, champ, valeur)
    db.commit()
    db.refresh(ecole)
    return ecole


# ---------------------------------------------------------------------------
# Annonces
# ---------------------------------------------------------------------------
@router.get("/annonces", summary="Liste des annonces")
def liste_annonces(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict:
    sid = sd.sid_ecole(db)
    annonces = db.execute(
        select(Annonce).where(Annonce.school_id == sid).order_by(Annonce.date)
    ).scalars().all()
    return {"annonces": [sd.annonce_to_dict(a) for a in annonces]}


@router.post("/annonces", summary="Créer une annonce (admin)")
def creer_annonce(
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_roles(ROLE_ADMIN)),
) -> dict:
    # Identifiant auto : A{max+1} (max numérique — A10 > A9 en ordre chaîne)
    sid = sd.sid_ecole(db)
    tous = db.execute(
        select(Annonce.id).where(Annonce.school_id == sid)
    ).scalars().all()
    num = max((int(a[1:]) for a in tous if a[:1] == "A" and a[1:].isdigit()), default=0) + 1
    annonce = Annonce(
        school_id=sid,
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
    return sd.annonce_to_dict(annonce)


@router.put("/annonces/{annonce_id}", summary="Modifier une annonce (admin)")
def modifier_annonce(
    annonce_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_roles(ROLE_ADMIN)),
) -> dict:
    annonce = sd.get_annonce(db, annonce_id)
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
    return sd.annonce_to_dict(annonce)


@router.delete("/annonces/{annonce_id}", response_model=MessageOut, summary="Supprimer une annonce (admin)")
def supprimer_annonce(
    annonce_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_roles(ROLE_ADMIN)),
) -> MessageOut:
    annonce = sd.get_annonce(db, annonce_id)
    if annonce is None:
        raise HTTPException(status_code=404, detail="Annonce introuvable.")
    db.delete(annonce)
    db.commit()
    return MessageOut(message="Annonce supprimée.")
