"""Routes d'authentification : connexion, inscription publique, gestion des comptes (admin)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import ROLE_ADMIN, ROLE_PARENT, get_current_user, require_roles
from app.database import get_db
from app.models import Ecole, User
from app.schemas import CompteIn, InscriptionIn, LoginIn, TokenOut, UserOut
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/v1/auth", tags=["authentification"])

# Rôles acceptés lors de la création d'un compte par un administrateur.
ROLES_CREABLES = ("Administrateur", "Professeur", "Élève", "Parent")


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


def _verifier_email_unique(db: Session, email: str) -> None:
    """Lève 409 si l'email est déjà utilisé (contrôle + contrainte)."""
    existant = db.scalar(select(User).where(User.email == email))
    if existant is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Un compte existe déjà avec cette adresse email.",
        )


def _creer_user(db: Session, nom: str, email: str, password: str, role: str) -> User:
    """Crée un utilisateur actif avec mot de passe haché (PBKDF2)."""
    nom = nom.strip()
    email = email.strip().lower()
    if not nom:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Le nom est obligatoire.")
    if len(password) < 6:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Le mot de passe doit contenir au moins 6 caractères.",
        )
    _verifier_email_unique(db, email)
    user = User(
        email=email,
        password_hash=hash_password(password),
        role=role,
        nom=nom[:80],
        actif=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _token_pour(user: User, db: Session) -> TokenOut:
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
    return _token_pour(user, db)


@router.post(
    "/inscription",
    response_model=TokenOut,
    status_code=status.HTTP_201_CREATED,
    summary="Inscription publique (compte Parent)",
)
def inscription(body: InscriptionIn, db: Session = Depends(get_db)) -> TokenOut:
    """Crée un compte Parent (accès au suivi des enfants) puis connecte.

    L'inscription publique est volontairement limitée au rôle Parent :
    les autres rôles sont créés par l'administration.
    """
    user = _creer_user(db, body.nom, body.email, body.password, ROLE_PARENT)
    return _token_pour(user, db)


@router.get(
    "/comptes",
    response_model=list[UserOut],
    summary="Liste des comptes (administrateur)",
)
def lister_comptes(
    _admin: User = Depends(require_roles(ROLE_ADMIN)),
    db: Session = Depends(get_db),
) -> list[UserOut]:
    users = db.scalars(select(User).order_by(User.id)).all()
    return [_vers_user_out(u) for u in users]


@router.post(
    "/comptes",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Créer un compte (administrateur)",
)
def creer_compte(
    body: CompteIn,
    _admin: User = Depends(require_roles(ROLE_ADMIN)),
    db: Session = Depends(get_db),
) -> UserOut:
    role = body.role.strip()
    if role not in ROLES_CREABLES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Rôle invalide. Choisissez parmi : " + ", ".join(ROLES_CREABLES) + ".",
        )
    user = _creer_user(db, body.nom, body.email, body.password, role)
    return _vers_user_out(user)


@router.get("/me", response_model=UserOut, summary="Profil de l'utilisateur courant")
def me(user: User = Depends(get_current_user)) -> UserOut:
    return _vers_user_out(user)
