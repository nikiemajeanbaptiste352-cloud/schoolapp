"""Phase 3 — « Rattachement » : résolution du rôle effectif par établissement.

Trois notions distinctes (architecture cible §III.1) :

1. **Identité** — la table `users` (une ligne par personne, email unique).
2. **Rôle fonctionnel** — `membres.role`, c'est-à-dire le rôle **dans une
   école donnée**. Une même identité peut être Professeur dans l'école 1 et
   Parent dans l'école 2.
3. **Permission** — les règles des routeurs (`exiger_role`, périmètre élève).

Politique de transition (compatibilité ascendante) :

- si un rattachement **existe** pour le couple (utilisateur, école courante),
  il **fait foi** : son `role` remplace `users.role` et son `statut` filtre
  l'accès (`actif` → autorisé, `invite`/`suspendu` → 403) ;
- si aucun rattachement n'existe, on retombe sur `users.role` / `users.school_id`
  (colonnes historiques). Ce repli permet aux bases déjà en production de
  continuer à fonctionner pendant la migration et sera retiré en Phase 4 une
  fois le remplissage terminé.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ROLES_MEMBRE, Ecole, Membership, User

# Statuts qui ouvrent l'accès.
STATUTS_ACCES = ("actif",)


# ---------------------------------------------------------------------------
# Lecture
# ---------------------------------------------------------------------------
def membres_de(db: Session, user_id: int) -> list[Membership]:
    """Tous les rattachements d'une identité, école croissante."""
    return list(
        db.scalars(
            select(Membership)
            .where(Membership.user_id == user_id)
            .order_by(Membership.school_id)
        )
    )


def membre_ecole(
    db: Session, user_id: int, school_id: int | None
) -> Membership | None:
    """Rattachement (utilisateur, école) ou `None`."""
    if school_id is None:
        return None
    return db.scalar(
        select(Membership).where(
            Membership.user_id == user_id,
            Membership.school_id == school_id,
        )
    )


def membre_actif(db: Session, user_id: int, school_id: int | None) -> Membership | None:
    """Rattachement utilisable (statut `actif`) ou `None`."""
    membre = membre_ecole(db, user_id, school_id)
    if membre is None or membre.statut not in STATUTS_ACCES:
        return None
    return membre


def role_effectif(
    db: Session, user: User, school_id: int | None = None
) -> str:
    """Rôle à appliquer pour l'école courante.

    Priorité au rattachement ; repli sur `users.role` tant que la table
    `membres` n'est pas remplie pour ce couple.
    """
    sid = school_id if school_id is not None else user.school_id
    membre = membre_ecole(db, user.id, sid)
    return membre.role if membre is not None else user.role


def ecoles_de(db: Session, user_id: int) -> list[tuple[Membership, Ecole | None]]:
    """Rattachements + fiches écoles, pour le sélecteur d'établissement."""
    lignes: list[tuple[Membership, Ecole | None]] = []
    for membre in membres_de(db, user_id):
        lignes.append((membre, db.get(Ecole, membre.school_id)))
    return lignes


# ---------------------------------------------------------------------------
# Écriture
# ---------------------------------------------------------------------------
def definir_membre(
    db: Session,
    user: User,
    school_id: int,
    role: str,
    statut: str = "actif",
    invite_par: int | None = None,
) -> Membership:
    """Crée ou met à jour le rattachement (utilisateur, école)."""
    if role not in ROLES_MEMBRE:
        raise ValueError(f"Rôle de rattachement inconnu : {role!r}")
    membre = membre_ecole(db, user.id, school_id)
    if membre is None:
        membre = Membership(
            user_id=user.id,
            school_id=school_id,
            role=role,
            statut=statut,
            invite_par=invite_par,
        )
        db.add(membre)
    else:
        membre.role = role
        membre.statut = statut
    db.flush()
    return membre


def assurer_membre(
    db: Session, user: User, school_id: int | None = None
) -> Membership | None:
    """Remplissage à la demande depuis `users.role` / `users.school_id`.

    Retourne le rattachement (existant ou créé), ou `None` si l'identité n'a
    aucun établissement exploitable. Le remplissage ne concerne **jamais** une
    école autre que celle de l'identité : ajouter un rattachement dans une
    autre école est une décision explicite (`definir_membre`, invitation).
    """
    sid = school_id if school_id is not None else user.school_id
    if sid is None or user.school_id != sid:
        return None
    existant = membre_ecole(db, user.id, sid)
    if existant is not None:
        return existant
    if user.role not in ROLES_MEMBRE:
        return None
    return definir_membre(db, user, sid, user.role, "actif")


def assurer_membres(db: Session, school_id: int | None = None) -> int:
    """Remplissage de masse, idempotent. Renvoie le nombre de rattachements créés.

    Appelée au démarrage (lifespan) et avant les listes de membres pour que la
    table se remplisse automatiquement, y compris après une restauration de
    base ou une insertion directe en SQL.
    """
    requete = select(User).where(User.school_id.is_not(None))
    if school_id is not None:
        requete = requete.where(User.school_id == school_id)
    crees = 0
    for user in db.scalars(requete):
        deja = membre_ecole(db, user.id, user.school_id)
        if deja is not None:
            continue
        if user.role not in ROLES_MEMBRE:
            continue
        db.add(
            Membership(
                user_id=user.id,
                school_id=user.school_id,
                role=user.role,
                statut="actif",
            )
        )
        crees += 1
    if crees:
        db.commit()
    return crees


def rattacher_fiche(db: Session, user: User, role: str) -> None:
    """Relie un compte à sa fiche métier (Enseignant) quand l'email correspond.

    Un rôle de rattachement « Professeur » sans `enseignant_id` rendrait le
    cahier de séances vide : on relie ici la fiche dont l'email correspond.
    """
    from app.models import Enseignant

    if role != "Professeur" or user.enseignant_id or user.school_id is None:
        return
    enseignant = db.scalar(
        select(Enseignant).where(
            Enseignant.school_id == user.school_id,
            Enseignant.email == user.email,
        )
    )
    if enseignant is not None:
        user.enseignant_id = enseignant.id
