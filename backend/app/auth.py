"""Dépendances d'authentification FastAPI — JWT + contrôle des rôles.

Rôles utilisés (alignés sur le front) :
    Administrateur, Professeur, Élève, Parent
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.security import decode_token
from app.services.sd import definir_ecole_courante

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
) -> Iterator[User]:
    """Résout l'utilisateur courant à partir du jeton Bearer.

    Dépendance génératrice : pose le contexte école (Phase 2) le temps de la
    requête, puis le réinitialise systématiquement (pas de fuite entre deux
    requêtes successives).
    """
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
    # Phase 2 — isolation school_id : l'école de la requête est celle de
    # l'utilisateur. Les comptes non rattachés retombent sur l'école par
    # défaut dans sd.py (comportement mono-établissement préservé).
    definir_ecole_courante(user.school_id)
    try:
        yield user
    finally:
        definir_ecole_courante(None)


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
