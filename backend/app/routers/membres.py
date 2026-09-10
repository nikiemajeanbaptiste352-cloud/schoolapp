"""Phase 3 — « Rattachement » : membres d'un établissement et invitations.

Cette brique répond à trois besoins de l'architecture cible (§III.1) :

1. **Séparer identité et rôle** — un compte (`users`) peut être rattaché à
   plusieurs établissements avec un rôle différent dans chacun ;
2. **Rattacher sans créer de compte** — la direction invite une adresse email :
   le compte n'est créé qu'à l'acceptation de l'invitation (code à 6 chiffres,
   même mécanisme que la connexion par email) ;
3. **Cloisonner** — toutes les routes d'administration ne voient que l'école
   du jeton (`sd.sid_ecole`), jamais les autres.

Convention de sécurité : un identifiant de rattachement inconnu **ou** situé
dans une autre école doit produire le même `404` (pas de fuite d'existence).
"""

from __future__ import annotations

import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import ROLE_ADMIN, get_current_user, require_roles
from app.config import settings
from app.database import get_db
from app.models import ROLES_MEMBRE, Ecole, InvitationMembre, Membership, User
from app.schemas import (
    EcoleActiveIn,
    MembreInvitationIn,
    MembreInvitationOut,
    MembreInvitationValidationIn,
    MembreOut,
    MembreRoleIn,
    MembreStatutIn,
    MonEcoleOut,
    TokenOut,
)
from app.security import hasher_code_verification, verifier_code_verification
from app.services import email as email_service
from app.services import sd
from app.services.comptes import creer_user, maintenant_utc, token_pour, valider_email
from app.services.membres import (
    assurer_membre,
    assurer_membres,
    definir_membre,
    ecoles_de,
    membre_ecole,
    rattacher_fiche,
)

router = APIRouter(prefix="/api/v1", tags=["rattachement"])

# Délai minimal entre deux envois de code d'invitation pour une même adresse.
ANTI_SPAM_SECONDES = 60
# Statuts modifiables par la direction (une invitation se valide par code).
STATUTS_MANIPULABLES = ("actif", "suspendu")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _membre_de_lec(dbm: Session, membre_id: int, school_id: int) -> Membership:
    """Rattachement de l'école courante, ou 404 (pas de fuite inter-écoles)."""
    membre = dbm.get(Membership, membre_id)
    if membre is None or membre.school_id != school_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rattachement introuvable dans cet établissement.",
        )
    return membre


def _compter_admins_actifs(db: Session, school_id: int) -> int:
    return len(
        db.scalars(
            select(Membership).where(
                Membership.school_id == school_id,
                Membership.role == ROLE_ADMIN,
                Membership.statut == "actif",
            )
        ).all()
    )


def _refuser_dernier_admin(db: Session, membre: Membership, action: str) -> None:
    """Empêche de se couper l'accès : il doit rester un administrateur actif."""
    if membre.role != ROLE_ADMIN or membre.statut != "actif":
        return
    if _compter_admins_actifs(db, membre.school_id) <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Impossible de {action} : c'est le dernier compte "
                "administrateur actif de l'établissement."
            ),
        )


def _vers_membre_out(db: Session, membre: Membership, user: User) -> MembreOut:
    return MembreOut(
        id=membre.id,
        user_id=user.id,
        nom=user.nom,
        email=user.email,
        role=membre.role,
        statut=membre.statut,
        actif=user.actif,
        eleve_id=user.eleve_id,
        enseignant_id=user.enseignant_id,
        cree_le=membre.cree_le.isoformat() if membre.cree_le else None,
    )


def _preparer_code(
    db: Session, school_id: int, email: str, role: str, invite_par: int
) -> tuple[InvitationMembre, str]:
    """Crée ou rafraîchit le code d'invitation (anti-spam 60 s)."""
    maintenant = maintenant_utc()
    ligne = db.scalar(
        select(InvitationMembre).where(
            InvitationMembre.school_id == school_id,
            InvitationMembre.email == email,
        )
    )
    if ligne is not None and ligne.created_at is not None:
        age = (maintenant - ligne.created_at.replace(tzinfo=None)).total_seconds()
        if 0 <= age < ANTI_SPAM_SECONDES:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    "Une invitation vient d'être envoyée à cette adresse. "
                    "Attendez une minute avant de renvoyer."
                ),
            )

    code = email_service.generer_code()
    if ligne is None:
        ligne = InvitationMembre(school_id=school_id, email=email)
        db.add(ligne)
    ligne.role = role
    ligne.code_hash = hasher_code_verification(code)
    ligne.expires_at = maintenant + timedelta(minutes=settings.code_expire_minutes)
    ligne.created_at = maintenant
    ligne.tentatives = 0
    ligne.invite_par = invite_par
    return ligne, code


# ---------------------------------------------------------------------------
# Membres de l'établissement (direction)
# ---------------------------------------------------------------------------
@router.get(
    "/membres",
    response_model=list[MembreOut],
    summary="Membres de l'établissement courant",
)
def lister_membres(
    _admin: User = Depends(require_roles(ROLE_ADMIN)),
    db: Session = Depends(get_db),
) -> list[MembreOut]:
    """Rattachements (actifs, invités, suspendus) de l'école du jeton."""
    sid = sd.sid_ecole(db)
    assurer_membres(db, sid)
    resultat: list[MembreOut] = []
    for membre in db.scalars(
        select(Membership).where(Membership.school_id == sid).order_by(Membership.id)
    ):
        user = db.get(User, membre.user_id)
        if user is not None:
            resultat.append(_vers_membre_out(db, membre, user))
    return resultat


def _expire_dans(expires_at) -> int:
    """Secondes restantes avant expiration d'un code (0 si déjà expiré)."""
    if expires_at is None:
        return 0
    restant = (expires_at.replace(tzinfo=None) - maintenant_utc()).total_seconds()
    return max(0, int(restant))


@router.get(
    "/membres/invitations",
    response_model=list[MembreInvitationOut],
    summary="Invitations en attente dans l'établissement",
)
def lister_invitations(
    _admin: User = Depends(require_roles(ROLE_ADMIN)),
    db: Session = Depends(get_db),
) -> list[MembreInvitationOut]:
    """Invitations non encore validées (adresses sans compte ou en attente)."""
    sid = sd.sid_ecole(db)
    ecole = db.get(Ecole, sid)
    maintenant = maintenant_utc()
    resultat: list[MembreInvitationOut] = []
    for ligne in db.scalars(
        select(InvitationMembre)
        .where(InvitationMembre.school_id == sid)
        .order_by(InvitationMembre.id)
    ):
        expire = ligne.expires_at is None or (
            ligne.expires_at.replace(tzinfo=None) < maintenant
        )
        resultat.append(
            MembreInvitationOut(
                id=ligne.id,
                email=ligne.email,
                role=ligne.role,
                statut="expire" if expire else "invite",
                ecole=ecole.nom if ecole else None,
                expire_dans=_expire_dans(ligne.expires_at),
                message=(
                    "Invitation expirée : renvoyez un code."
                    if expire
                    else "Invitation en attente de validation."
                ),
                code_envoye=not expire,
            )
        )
    return resultat


@router.post(
    "/membres",
    response_model=MembreInvitationOut,
    status_code=status.HTTP_201_CREATED,
    summary="Inviter / rattacher une adresse email",
)
def inviter_membre(
    body: MembreInvitationIn,
    admin: User = Depends(require_roles(ROLE_ADMIN)),
    db: Session = Depends(get_db),
) -> MembreInvitationOut:
    """Rattache une adresse à l'école avec un rôle, par code envoyé par email.

    - adresse **inconnue** → aucun compte n'est créé ici : il sera créé à
      l'acceptation de l'invitation (l'email prouve l'identité) ;
    - adresse **connue** → un rattachement en attente (`invite`) est ajouté ;
      son rôle dans les autres établissements n'est pas modifié.
    """
    sid = sd.sid_ecole(db)
    email = valider_email(body.email)
    role = (body.role or "").strip()
    if role not in ROLES_MEMBRE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Rôle invalide. Choisissez parmi : " + ", ".join(ROLES_MEMBRE) + ".",
        )
    if not settings.email_active:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="L'envoi d'emails n'est pas encore configuré sur ce serveur.",
        )

    ecole = db.get(Ecole, sid)
    user = db.scalar(select(User).where(User.email == email))
    if user is not None:
        # Remplissage à la demande : un compte déjà rattaché à SON école ne
        # doit pas être rétrogradé en « invitation » par simple oubli.
        assurer_membre(db, user)
        existant = membre_ecole(db, user.id, sid)
        if existant is not None and existant.statut == "actif":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cette adresse est déjà membre de l'établissement.",
            )
        definir_membre(db, user, sid, role, "invite", invite_par=admin.id)

    ligne, code = _preparer_code(db, sid, email, role, admin.id)
    db.commit()
    db.refresh(ligne)

    try:
        email_service.envoyer_invitation(
            email, code, ecole.nom if ecole else "l'établissement", role
        )
    except email_service.EmailNonConfigure as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e) or "Envoi d'emails non configuré.",
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e) or "L'envoi de l'invitation a échoué.",
        )

    return MembreInvitationOut(
        id=ligne.id,
        email=ligne.email,
        role=ligne.role,
        statut="invite",
        ecole=ecole.nom if ecole else None,
        expire_dans=settings.code_expire_minutes * 60,
        message="Invitation envoyée. Le rôle sera actif dès validation du code.",
        code_envoye=True,
    )


@router.post(
    "/membres/{membre_id}/invitation",
    response_model=MembreInvitationOut,
    summary="Renvoyer le code d'invitation",
)
def renvoyer_invitation(
    membre_id: int,
    admin: User = Depends(require_roles(ROLE_ADMIN)),
    db: Session = Depends(get_db),
) -> MembreInvitationOut:
    """Regénère un code pour un rattachement en attente."""
    sid = sd.sid_ecole(db)
    membre = _membre_de_lec(db, membre_id, sid)
    if membre.statut != "invite":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ce membre a déjà validé son rattachement.",
        )
    if not settings.email_active:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="L'envoi d'emails n'est pas encore configuré sur ce serveur.",
        )
    user = db.get(User, membre.user_id)
    email = user.email if user is not None else ""
    ecole = db.get(Ecole, sid)
    ligne, code = _preparer_code(db, sid, email, membre.role, admin.id)
    db.commit()
    db.refresh(ligne)
    try:
        email_service.envoyer_invitation(
            email, code, ecole.nom if ecole else "l'établissement", membre.role
        )
    except email_service.EmailNonConfigure as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e) or "Envoi d'emails non configuré.",
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e) or "L'envoi de l'invitation a échoué.",
        )
    return MembreInvitationOut(
        id=ligne.id,
        email=email,
        role=membre.role,
        statut="invite",
        ecole=ecole.nom if ecole else None,
        expire_dans=settings.code_expire_minutes * 60,
        message="Nouveau code d'invitation envoyé.",
        code_envoye=True,
    )


@router.post(
    "/membres/invitations/valider",
    response_model=TokenOut,
    summary="Valider une invitation et se connecter",
)
def valider_invitation(
    body: MembreInvitationValidationIn, db: Session = Depends(get_db)
) -> TokenOut:
    """Consomme le code reçu, active le rattachement et connecte le compte.

    Route **publique** (comme `/auth/code/valider`) : à ce stade l'invité n'a
    pas encore de compte. L'email vérifié fait foi d'identité.
    """
    email = valider_email(body.email)
    maintenant = maintenant_utc()

    lignes = db.scalars(
        select(InvitationMembre).where(InvitationMembre.email == email)
    ).all()
    if not lignes:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Aucune invitation en attente pour cette adresse.",
        )

    retenue: InvitationMembre | None = None
    expiree = False
    for ligne in lignes:
        if ligne.expires_at is not None:
            ligne.expires_at = ligne.expires_at.replace(tzinfo=None)
        if ligne.expires_at is None or ligne.expires_at < maintenant:
            expiree = True
            continue
        if ligne.tentatives >= 5:
            continue
        if verifier_code_verification((body.code or "").strip(), ligne.code_hash):
            retenue = ligne
            break
        ligne.tentatives += 1
        db.commit()

    if retenue is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Code invalide ou expiré. Demandez une nouvelle invitation."
                if not expiree
                else "Invitation expirée. Demandez une nouvelle invitation."
            ),
        )

    sid = retenue.school_id
    role = retenue.role
    invite_par = retenue.invite_par
    # Usage unique : l'invitation est consommée.
    db.delete(retenue)
    db.commit()

    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        nom = (body.nom or "").strip() or email.split("@")[0]
        mot_de_passe = (body.password or "").strip() or secrets.token_urlsafe(24)
        user = creer_user(db, nom, email, mot_de_passe, role, school_id=sid)
    if not user.actif:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Compte désactivé. Contactez l'administration.",
        )

    definir_membre(db, user, sid, role, "actif", invite_par=invite_par)
    rattacher_fiche(db, user, role)
    # L'école de travail devient celle de l'invitation si le compte n'en avait
    # pas d'autre : le contexte de la prochaine requête sera donc correct.
    if user.school_id is None:
        user.school_id = sid
    db.commit()
    db.refresh(user)

    # Phase 3 n'implémente pas encore la bascule d'école *dans la session* :
    # l'école indiquée ici est celle du rattachement validé.
    return token_pour(user, db)


@router.put(
    "/membres/{membre_id}/role",
    response_model=MembreOut,
    summary="Changer le rôle d'un membre",
)
def changer_role(
    membre_id: int,
    body: MembreRoleIn,
    _admin: User = Depends(require_roles(ROLE_ADMIN)),
    db: Session = Depends(get_db),
) -> MembreOut:
    sid = sd.sid_ecole(db)
    membre = _membre_de_lec(db, membre_id, sid)
    role = (body.role or "").strip()
    if role not in ROLES_MEMBRE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Rôle invalide. Choisissez parmi : " + ", ".join(ROLES_MEMBRE) + ".",
        )
    if role != membre.role and membre.role == ROLE_ADMIN:
        _refuser_dernier_admin(db, membre, "changer le rôle")
    membre.role = role
    user = db.get(User, membre.user_id)
    if user is not None:
        # Miroir de compatibilité sur l'identité (le rattachement fait foi).
        user.role = role
        rattacher_fiche(db, user, role)
    db.commit()
    db.refresh(membre)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Compte introuvable pour ce rattachement.",
        )
    return _vers_membre_out(db, membre, user)


@router.put(
    "/membres/{membre_id}/statut",
    response_model=MembreOut,
    summary="Suspendre / réactiver un membre",
)
def changer_statut(
    membre_id: int,
    body: MembreStatutIn,
    _admin: User = Depends(require_roles(ROLE_ADMIN)),
    db: Session = Depends(get_db),
) -> MembreOut:
    sid = sd.sid_ecole(db)
    membre = _membre_de_lec(db, membre_id, sid)
    statut = (body.statut or "").strip()
    if statut not in STATUTS_MANIPULABLES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Statut invalide. Choisissez : " + ", ".join(STATUTS_MANIPULABLES) + ".",
        )
    if statut == "suspendu" and membre.statut == "actif":
        _refuser_dernier_admin(db, membre, "suspendre ce compte")
    membre.statut = statut
    db.commit()
    db.refresh(membre)
    user = db.get(User, membre.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Compte introuvable pour ce rattachement.",
        )
    return _vers_membre_out(db, membre, user)


@router.delete(
    "/membres/{membre_id}",
    response_model=dict,
    summary="Retirer un membre de l'établissement",
)
def retirer_membre(
    membre_id: int,
    _admin: User = Depends(require_roles(ROLE_ADMIN)),
    db: Session = Depends(get_db),
) -> dict:
    """Supprime le rattachement (l'invitation en attente est révoquée).

    Refus (400) si c'est l'établissement **actif** du compte et qu'il n'en a
    pas d'autre : la suspension (`PUT /statut`) coupe l'accès sans casser le
    contexte de l'école.
    """
    sid = sd.sid_ecole(db)
    membre = _membre_de_lec(db, membre_id, sid)
    _refuser_dernier_admin(db, membre, "retirer ce compte")
    user = db.get(User, membre.user_id)

    autres = []
    if user is not None:
        autres = [m for m in ecoles_de(db, user.id) if m[0].id != membre.id]
    if user is not None and user.school_id == sid and not autres:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Ce compte n'a pas d'autre établissement : suspendez le "
                "rattachement au lieu de le supprimer."
            ),
        )

    # Révocation de l'invitation en attente éventuelle (même adresse/école).
    email = user.email if user is not None else None
    if email:
        for ligne in db.scalars(
            select(InvitationMembre).where(
                InvitationMembre.school_id == sid,
                InvitationMembre.email == email,
            )
        ).all():
            db.delete(ligne)

    db.delete(membre)
    if user is not None and user.school_id == sid and autres:
        autre = autres[0][0]
        user.school_id = autre.school_id
        user.role = autre.role
    db.commit()
    return {"message": "Membre retiré de l'établissement."}


# ---------------------------------------------------------------------------
# Espace personnel — mes établissements
# ---------------------------------------------------------------------------
@router.get(
    "/mon-espace/ecoles",
    response_model=list[MonEcoleOut],
    summary="Mes établissements (sélecteur)",
)
def mes_ecoles(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[MonEcoleOut]:
    """Tous les rattachements du compte connecté, avec l'école active."""
    assurer_membre(db, user)
    db.commit()
    resultat: list[MonEcoleOut] = []
    for membre, ecole in ecoles_de(db, user.id):
        resultat.append(
            MonEcoleOut(
                school_id=membre.school_id,
                nom=ecole.nom if ecole else "Établissement",
                sigle=ecole.sigle if ecole else "",
                role=membre.role,
                statut=membre.statut,
                active=membre.school_id == user.school_id,
            )
        )
    return resultat


@router.post(
    "/mon-espace/ecole-active",
    response_model=TokenOut,
    summary="Basculer d'établissement",
)
def activer_ecole(
    body: EcoleActiveIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TokenOut:
    """Change l'établissement de travail : un nouveau jeton est renvoyé.

    Le rattachement visé doit exister **et** être actif ; sinon `404`
    (un compte ne peut pas « deviner » les autres établissements).
    """
    membre = membre_ecole(db, user.id, body.school_id)
    if membre is None or membre.statut != "actif":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aucun rattachement actif avec cet établissement.",
        )
    user.school_id = membre.school_id
    user.role = membre.role
    db.commit()
    db.refresh(user)
    return token_pour(user, db)
