"""Routes d'authentification : connexion, inscription publique, gestion des
comptes (admin), connexion par code email et « Se connecter avec Google »."""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import Request as UrlRequest
from urllib.request import urlopen
from urllib.error import HTTPError as UrlHTTPError

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import ROLE_ADMIN, ROLE_PARENT, get_current_user, require_roles
from app.config import settings
from app.database import get_db
from app.models import Ecole, EmailCode, User
from app.schemas import (
    CodeDemandeIn,
    CodeValidationIn,
    CompteIn,
    InscriptionIn,
    LoginIn,
    TokenOut,
    UserOut,
)
from app.security import (
    create_access_token,
    decode_token,
    hash_password,
    hasher_code_verification,
    verifier_code_verification,
    verify_password,
)
from app.services import email as email_service

router = APIRouter(prefix="/api/v1/auth", tags=["authentification"])

# Rôles acceptés lors de la création d'un compte par un administrateur.
ROLES_CREABLES = ("Administrateur", "Professeur", "Élève", "Parent")

# Endpoints Google OAuth 2.0
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


def _maintenant_utc() -> datetime:
    """Horodatage UTC « naïf » (compatible SQLite et PostgreSQL)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _valider_email(email: str) -> str:
    """Normalise (minuscules) et valide une adresse email ; 422 sinon."""
    email = (email or "").strip().lower()
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Adresse email invalide.",
        )
    return email


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


@router.get(
    "/options",
    summary="Méthodes de connexion actives (front)",
)
def options_auth() -> dict:
    """Indique au front quelles méthodes de connexion sont disponibles."""
    return {
        "google": settings.google_active,
        "code_email": settings.email_active,
    }


# ---------------------------------------------------------------------------
# Connexion par code envoyé par email (sans mot de passe)
# ---------------------------------------------------------------------------
@router.post(
    "/code/demander",
    summary="Envoyer un code de connexion par email",
)
def demander_code(body: CodeDemandeIn, db: Session = Depends(get_db)) -> dict:
    """Envoie un code à 6 chiffres à l'adresse indiquée (10 min).

    Accessible à toute adresse : si un compte existe déjà avec cet email, le
    code permet de s'y connecter ; sinon un compte Parent sera créé lors de la
    validation (l'email prouve l'identité).
    """
    email = _valider_email(body.email)
    if not settings.email_active:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="L'envoi d'emails n'est pas encore configuré sur ce serveur.",
        )

    ligne = db.get(EmailCode, email)
    maintenant = _maintenant_utc()
    # Anti-spam : un seul code toutes les 60 secondes par adresse.
    if ligne is not None and ligne.created_at is not None:
        age = (maintenant - ligne.created_at.replace(tzinfo=None)).total_seconds()
        if 0 <= age < 60:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Un code vient d'être envoyé. Attendez une minute avant de redemander.",
            )

    code = email_service.generer_code()
    expire = maintenant + timedelta(minutes=settings.code_expire_minutes)
    if ligne is None:
        ligne = EmailCode(email=email)
        db.add(ligne)
    ligne.code_hash = hasher_code_verification(code)
    ligne.expires_at = expire
    ligne.created_at = maintenant
    ligne.tentatives = 0

    try:
        db.commit()
        email_service.envoyer_email_code(email, code)
    except email_service.EmailNonConfigure as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e) or "Envoi d'emails non configuré.",
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e) or "L'envoi de l'email a échoué.",
        )
    return {
        "message": "Code envoyé par email.",
        "delai": settings.code_expire_minutes * 60,
    }


@router.post(
    "/code/valider",
    response_model=TokenOut,
    summary="Valider le code reçu par email et se connecter",
)
def valider_code(body: CodeValidationIn, db: Session = Depends(get_db)) -> TokenOut:
    """Vérifie le code, crée le compte Parent si besoin, puis connecte."""
    email = _valider_email(body.email)
    ligne = db.get(EmailCode, email)
    maintenant = _maintenant_utc()
    if ligne is not None and ligne.expires_at is not None:
        ligne.expires_at = ligne.expires_at.replace(tzinfo=None)

    if ligne is None or ligne.expires_at is None or ligne.expires_at < maintenant:
        if ligne is not None:
            db.delete(ligne)
            db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Code invalide ou expiré. Demandez un nouveau code.",
        )
    if ligne.tentatives >= 5:
        db.delete(ligne)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Trop de tentatives. Demandez un nouveau code.",
        )

    if not verifier_code_verification((body.code or "").strip(), ligne.code_hash):
        ligne.tentatives += 1
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Code invalide ou expiré.",
        )

    # Code correct → consommé (usage unique).
    db.delete(ligne)
    db.commit()

    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        # Premier accès avec cette adresse → compte Parent automatique.
        nom = (body.nom or "").strip() or "Parent"
        user = User(
            email=email,
            password_hash=hash_password(secrets.token_urlsafe(24)),
            role=ROLE_PARENT,
            nom=nom[:80],
            actif=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    if not user.actif:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Compte désactivé. Contactez l'administration.",
        )
    return _token_pour(user, db)


# ---------------------------------------------------------------------------
# « Se connecter avec Google » (OAuth 2.0)
# ---------------------------------------------------------------------------
@router.get("/google", summary="Connexion Google — redirection vers Google")
def connexion_google(request: Request) -> RedirectResponse:
    """Redirige le navigateur vers l'écran de consentement Google."""
    if not settings.google_active:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La connexion Google n'est pas configurée (identifiants manquants).",
        )
    redirect_uri = settings.google_redirect_uri or str(request.url_for("google_callback"))
    etat = create_access_token(
        "etat-oauth", extra={"usage": "oauth-state"}, expire_minutes=10
    )
    parametres = urlencode(
        {
            "client_id": settings.google_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "access_type": "online",
            "prompt": "select_account",
            "state": etat,
        }
    )
    return RedirectResponse(f"{GOOGLE_AUTH_URL}?{parametres}")


@router.get("/google/callback", summary="Retour de Google — échange du code")
def google_callback(
    request: Request,
    db: Session = Depends(get_db),
    code: str = Query(""),
    state: str = Query(""),
    error: str | None = Query(None),
) -> RedirectResponse:
    """Reçoit le code de Google, échange, puis connecte (ou crée) l'utilisateur.

    Termine par une redirection vers pages/oauth-callback.html qui mémorise le
    jeton dans le navigateur (fragment d'URL, jamais envoyé au serveur).
    """
    base_front = str(request.base_url).rstrip("/")

    def vers_front(parametres: dict) -> RedirectResponse:
        fragment = urlencode(parametres)
        return RedirectResponse(f"{base_front}/pages/oauth-callback.html#{fragment}")

    if error:
        return vers_front({"erreur": "acces_refuse"})
    if not code or not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Paramètres OAuth manquants.",
        )
    try:
        payload = decode_token(state)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="État OAuth invalide."
        )
    if payload.get("usage") != "oauth-state":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="État OAuth invalide."
        )
    if not settings.google_active:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La connexion Google n'est pas configurée.",
        )

    # Échange du code d'autorisation contre un jeton d'accès.
    redirect_uri = settings.google_redirect_uri or str(request.url_for("google_callback"))
    corps = urlencode(
        {
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
    ).encode("utf-8")
    try:
        with urlopen(
            UrlRequest(
                GOOGLE_TOKEN_URL,
                data=corps,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            ),
            timeout=20,
        ) as rep:
            jeton = json.load(rep)
    except UrlHTTPError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Google a refusé le code d'autorisation.",
        )
    acces = jeton.get("access_token")
    if not acces:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Aucun jeton d'accès reçu de Google.",
        )

    # Profil Google (l'email vérifié fait foi d'identité).
    try:
        with urlopen(
            UrlRequest(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {acces}"},
            ),
            timeout=20,
        ) as rep:
            info = json.load(rep)
    except UrlHTTPError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Impossible de récupérer le profil Google.",
        )

    email = (info.get("email") or "").strip().lower()
    if not email or not info.get("email_verified"):
        return vers_front({"erreur": "email_non_verifie"})

    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        nom = (info.get("name") or "").strip() or "Utilisateur Google"
        user = User(
            email=email,
            password_hash=hash_password(secrets.token_urlsafe(24)),
            role=ROLE_PARENT,
            nom=nom[:80],
            actif=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    if not user.actif:
        return vers_front({"erreur": "compte_desactive"})

    token = _token_pour(user, db)
    return vers_front(
        {
            "token": token.access_token,
            "email": user.email,
            "role": user.role,
            "nom": user.nom,
            "ecole": token.ecole or "",
            "annee": token.annee or "",
        }
    )


@router.get("/me", response_model=UserOut, summary="Profil de l'utilisateur courant")
def me(user: User = Depends(get_current_user)) -> UserOut:
    return _vers_user_out(user)
