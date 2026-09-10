"""Dépendances d'authentification FastAPI — JWT + contrôle des rôles.

Rôles utilisés (alignés sur le front) :
    Administrateur, Professeur, Surveillant, Élève, Parent

Phase 3 — « Rattachement » : le rôle appliqué est celui du **rattachement
actif** (`membres.role`) pour l'école de la requête ; `users.role` ne sert
plus que de repli tant que la table `membres` n'est pas remplie (migration
progressive, cf. `app/services/membres.py`).
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Membership, User
from app.security import decode_token
from app.services.membres import role_effectif
from app.services.sd import definir_ecole_courante

_bearer = HTTPBearer(auto_error=False)

# Alias de code pour plus de lisibilité
ROLE_ADMIN = "Administrateur"
ROLE_PROF = "Professeur"
ROLE_SURVEILLANT = "Surveillant"
ROLE_ELEVE = "Élève"
ROLE_PARENT = "Parent"


def _erreur_401(detail: str = "Authentification requise.") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _verifier_rattachement(db: Session, user: User) -> None:
    """Refuse l'accès si le rattachement de l'école courante n'est pas actif.

    - aucun rattachement → toléré (repli `users.role`, migration en cours) ;
    - `actif`            → autorisé ;
    - `invite`           → 403 « invitation non validée » ;
    - `suspendu`         → 403 « rattachement suspendu ».
    """
    if user.school_id is None:
        return
    membre = (
        db.query(Membership)
        .filter(
            Membership.user_id == user.id,
            Membership.school_id == user.school_id,
        )
        .one_or_none()
    )
    if membre is None or membre.statut == "actif":
        return
    if membre.statut == "invite":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invitation non validée pour cet établissement.",
        )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Rattachement suspendu pour cet établissement.",
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
        _verifier_rattachement(db, user)
        yield user
    finally:
        definir_ecole_courante(None)


def require_roles(*roles: str):
    """Retourne une dépendance exigeant l'un des rôles indiqués.

    Le rôle comparé est le **rôle effectif** dans l'école courante
    (`membres.role` s'il existe, sinon `users.role`).
    """

    def _verif(
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        if role_effectif(db, user) not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Droits insuffisants pour cette opération.",
            )
        return user

    return _verif
