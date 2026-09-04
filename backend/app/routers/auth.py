"""Routes d'authentification : POST /api/v1/auth/login, GET /api/v1/auth/me."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Ecole, User
from app.schemas import LoginIn, TokenOut, UserOut
from app.security import create_access_token, verify_password

router = APIRouter(prefix="/api/v1/auth", tags=["authentification"])


def _vers_user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        role=user.role,
        nom=user.nom,
        actif=user.actif,
        eleve_id=user.eleve_id,
        enseignant_id=user.enseignant_id,
        parent_id=user.parent_id,
    )


@router.post("/login", response_model=TokenOut, summary="Connexion (jeton JWT)")
def login(body: LoginIn, db: Session = Depends(get_db)) -> TokenOut:
    email = body.email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou mot de passe incorrect.",
        )
    if not user.actif:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Compte désactivé. Contactez l'administration.",
        )

    token = create_access_token(
        str(user.id),
        extra={"role": user.role, "email": user.email},
    )
    ecole = db.scalar(select(Ecole).limit(1))
    return TokenOut(
        access_token=token,
        user=_vers_user_out(user),
        ecole=ecole.nom if ecole else None,
        annee=ecole.annee if ecole else None,
    )


@router.get("/me", response_model=UserOut, summary="Profil de l'utilisateur courant")
def me(user: User = Depends(get_current_user)) -> UserOut:
    return _vers_user_out(user)
