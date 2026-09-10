"""Création et validation des comptes — helpers partagés (Phase 3).

Ces fonctions étaient privées dans `app/routers/auth.py` ; elles sont
mutualisées ici pour que le routeur des rattachements (`routers/membres.py`)
puisse créer un compte invité sans dupliquer les règles (email unique,
mot de passe minimum, hachage PBKDF2).
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Ecole, User
from app.schemas import TokenOut, UserOut
from app.security import create_access_token, hash_password
from app.services import sd
from app.services.membres import role_effectif


def maintenant_utc() -> datetime:
    """Horodatage UTC « naïf » (compatible SQLite et PostgreSQL)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def valider_email(email: str) -> str:
    """Normalise (minuscules) et valide une adresse email ; 422 sinon."""
    email = (email or "").strip().lower()
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Adresse email invalide.",
        )
    return email


def vers_user_out(user: User, role: str | None = None) -> UserOut:
    """Projection publique d'un compte (jamais de `password_hash`).

    `role` permet d'exposer le **rôle effectif** de l'école courante
    (`membres.role`) plutôt que la colonne historique `users.role`.
    """
    return UserOut(
        id=user.id,
        email=user.email,
        role=role or user.role,
        nom=user.nom,
        actif=user.actif,
        eleve_id=user.eleve_id,
        enseignant_id=user.enseignant_id,
        parent_id=user.parent_id,
    )


def verifier_email_unique(db: Session, email: str) -> None:
    """Lève 409 si l'email est déjà utilisé (contrôle + contrainte)."""
    existant = db.scalar(select(User).where(User.email == email))
    if existant is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Un compte existe déjà avec cette adresse email.",
        )


def creer_user(
    db: Session,
    nom: str,
    email: str,
    password: str,
    role: str,
    school_id: int | None = None,
) -> User:
    """Crée un utilisateur actif avec mot de passe haché (PBKDF2).

    Ne crée **pas** le rattachement : l'appelant décide du statut
    (`actif` pour une création directe, `invite` pour une invitation).
    """
    nom = nom.strip()
    email = email.strip().lower()
    if not nom:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Le nom est obligatoire."
        )
    if len(password) < 6:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Le mot de passe doit contenir au moins 6 caractères.",
        )
    verifier_email_unique(db, email)
    user = User(
        email=email,
        password_hash=hash_password(password),
        role=role,
        nom=nom[:80],
        actif=True,
        school_id=school_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def token_pour(user: User, db: Session) -> TokenOut:
    """Jeton JWT + école affichée au front (Phase 3 : rôle effectif)."""
    role = role_effectif(db, user)
    token = create_access_token(
        str(user.id),
        extra={"role": role, "email": user.email},
    )
    # École affichée : celle du compte si rattaché, sinon l'école par défaut du
    # déploiement (résolution non stricte : la connexion ne doit jamais échouer
    # à cause d'une ambiguïté de contexte).
    sid = user.school_id if user.school_id is not None else sd.ecole_principale(db)
    ecole = db.scalar(select(Ecole).where(Ecole.id == sid).limit(1))
    return TokenOut(
        access_token=token,
        user=vers_user_out(user, role=role),
        ecole=ecole.nom if ecole else None,
        annee=ecole.annee if ecole else None,
    )
