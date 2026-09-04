"""Dépendances d'authentification FastAPI — JWT + contrôle des rôles.

Rôles utilisés (alignés sur le front) :
    Administrateur, Professeur, Élève, Parent
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.security import decode_token

_bearer = HTTPBearer(auto_error=False)

# Alias de code pour plus de lisibilité
ROLE_ADMIN = "Administrateur"
ROLE_PROF = "Professeur"
ROLE_ELEVE = "Élève"
ROLE_PARENT = "Parent"


def _erreur_401(detail: str = "Authentification requise.") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """Résout l'utilisateur courant à partir du jeton Bearer."""
    if credentials is None:
        raise _erreur_401()
    try:
        payload = decode_token(credentials.credentials)
    except Exception:
        raise _erreur_401("Jeton invalide ou expiré.")
    sub = payload.get("sub")
    if sub is None:
        raise _erreur_401()
    user = db.get(User, int(sub))
    if user is None:
        raise _erreur_401("Utilisateur introuvable.")
    if not user.actif:
        raise _erreur_401("Compte désactivé.")
    return user


def require_roles(*roles: str):
    """Retourne une dépendance exigeant l'un des rôles indiqués."""

    def _verif(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Droits insuffisants pour cette opération.",
            )
        return user

    return _verif
