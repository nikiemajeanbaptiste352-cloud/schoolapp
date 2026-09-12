"""Phase 1 — Périmètre de visibilité : source de vérité unique du cloisonnement.

Problème corrigé
----------------
Plusieurs routeurs comparaient `users.role` (colonne **historique**) au lieu du
**rôle effectif** de l'établissement courant (`membres.role`), et
`GET /api/v1/etat` renvoyait l'établissement entier à n'importe quel rôle
connecté. Conséquence : un compte Parent ou Élève fraîchement inscrit
recevait les élèves, notes, présences et paiements de **tous les autres**.

Règle unique
------------
**Aucune décision de périmètre ne lit `user.role`.** Tout passe par
`role_courant()`, qui délègue à `services.membres.role_effectif()`
(rattachement de l'école courante ; repli transitoire sur `users.role` tant
que la table `membres` n'est pas remplie — cf. Phase 4).

Matrice appliquée
-----------------
======================  ================  =================  ==========  ==========
Rôle                    élèves            notes              présences   finances
======================  ================  =================  ==========  ==========
Administrateur          tous              toutes             toutes      toutes
Professeur              tous              **ses matières**   toutes      aucune
Surveillant             tous              aucune             toutes      aucune
Élève                   lui seul          les siennes        les siennes les siennes
Parent                  ses enfants       de ses enfants     idem        idem
(inconnu / suspendu)    aucun             aucune             aucune      aucune
======================  ================  =================  ==========  ==========

Convention de retour : `None` signifie « tout l'établissement », un `set()`
vide signifie « rien ». Les appelants ne doivent jamais confondre les deux.

Phase 2 — capacités de l'interface
----------------------------------
Les mêmes listes servent au navigateur : `capacites()` renvoie les pages et
les opérations autorisées, que `js/ui.js` se contente d'afficher. Aucune
décision d'habilitation n'est donc prise côté client.
"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import (
    ROLE_ADMIN,
    ROLE_ELEVE,
    ROLE_PARENT,
    ROLE_PROF,
    ROLE_SURVEILLANT,
)
from app.models import Eleve, Parent, User
from app.services import membres, sd

# --- Familles de rôles ------------------------------------------------------
ROLES_TOUS_ELEVES = (ROLE_ADMIN, ROLE_PROF, ROLE_SURVEILLANT)
ROLES_NOTES = (ROLE_ADMIN, ROLE_PROF)
ROLES_PRESENCES = (ROLE_ADMIN, ROLE_PROF, ROLE_SURVEILLANT)
ROLES_FINANCE = (ROLE_ADMIN,)
ROLES_ANNUAIRE = (ROLE_ADMIN, ROLE_PROF, ROLE_SURVEILLANT)


# ---------------------------------------------------------------------------
# Rôle courant
# ---------------------------------------------------------------------------
def role_courant(db: Session, user: User) -> str:
    """Rôle effectif dans l'établissement courant (jamais `users.role` brut)."""
    return membres.role_effectif(db, user)


def est_direction(db: Session, user: User) -> bool:
    return role_courant(db, user) == ROLE_ADMIN


def est_encadrement(db: Session, user: User) -> bool:
    """Administrateur ou Professeur (corps enseignant)."""
    return role_courant(db, user) in ROLES_NOTES


def est_vie_scolaire(db: Session, user: User) -> bool:
    """Administrateur ou Surveillant (présences, discipline)."""
    return role_courant(db, user) in ROLES_PRESENCES


def peut_voir_notes(db: Session, user: User) -> bool:
    return role_courant(db, user) in ROLES_NOTES


def peut_voir_finances(db: Session, user: User) -> bool:
    return role_courant(db, user) in ROLES_FINANCE


def peut_voir_annuaire(db: Session, user: User) -> bool:
    """Coordonnées (téléphone / email) des enseignants."""
    return role_courant(db, user) in ROLES_ANNUAIRE


# ---------------------------------------------------------------------------
# Périmètre « élèves »
# ---------------------------------------------------------------------------
def _eleves_lies(db: Session, user: User) -> set[str]:
    """Identifiants des élèves rattachés personnellement au compte."""
    role = role_courant(db, user)
    if role == ROLE_ELEVE:
        return {user.eleve_id} if user.eleve_id else set()
    if role == ROLE_PARENT:
        if not user.parent_id:
            return set()
        parent: Parent | None = db.get(Parent, user.parent_id)
        if parent is None:
            return set()
        return {e.id for e in parent.enfants}
    return set()


def _perimetre_eleves(
    db: Session, user: User, roles_complets: tuple[str, ...]
) -> set[str] | None:
    """None = tous les élèves de l'établissement ; sinon ensemble **fermé**."""
    if role_courant(db, user) in roles_complets:
        return None
    return _eleves_lies(db, user)


def ids_eleves_autorises(db: Session, user: User) -> set[str] | None:
    """Élèves consultables (fiches, listes, emplois du temps nominatifs)."""
    return _perimetre_eleves(db, user, ROLES_TOUS_ELEVES)


def ids_eleves_notes(db: Session, user: User) -> set[str] | None:
    """Élèves dont les notes sont lisibles. Surveillant → aucun."""
    return _perimetre_eleves(db, user, ROLES_NOTES)


def ids_eleves_presences(db: Session, user: User) -> set[str] | None:
    """Élèves dont les présences sont lisibles."""
    return _perimetre_eleves(db, user, ROLES_PRESENCES)


def ids_eleves_finance(db: Session, user: User) -> set[str] | None:
    """Élèves dont les paiements sont lisibles.

    Professeur et Surveillant n'ont **aucun** accès à la finance : l'ensemble
    renvoyé est vide (et non `None`).
    """
    return _perimetre_eleves(db, user, ROLES_FINANCE)


def eleves_visibles(db: Session, user: User) -> list[Eleve]:
    """Élèves de l'établissement courant réduits au périmètre du compte."""
    sid = sd.sid_ecole(db)
    ids = ids_eleves_autorises(db, user)
    if ids is not None and not ids:
        return []
    stmt = select(Eleve).where(Eleve.school_id == sid)
    if ids is not None:
        stmt = stmt.where(Eleve.id.in_(ids))
    return list(db.execute(stmt.order_by(Eleve.id)).scalars())


def peut_voir_eleve(db: Session, user: User, eleve_id: str) -> bool:
    ids = ids_eleves_autorises(db, user)
    return ids is None or eleve_id in ids


def exiger_eleve_visible(db: Session, user: User, eleve_id: str) -> None:
    if not peut_voir_eleve(db, user, eleve_id):
        raise HTTPException(status_code=403, detail="Accès refusé à cette fiche élève.")


def peut_voir_classe(db: Session, user: User, classe_id: str) -> bool:
    """Classe consultable : toutes pour l'encadrement, sinon celles où le
    compte a au moins un élève rattaché."""
    ids = ids_eleves_autorises(db, user)
    if ids is None:
        return True
    if not ids:
        return False
    lie = db.execute(
        select(Eleve.id).where(
            Eleve.school_id == sd.sid_ecole(db),
            Eleve.classe_id == classe_id,
            Eleve.id.in_(ids),
        )
    ).first()
    return lie is not None


def exiger_classe_visible(db: Session, user: User, classe_id: str) -> None:
    if not peut_voir_classe(db, user, classe_id):
        raise HTTPException(status_code=403, detail="Accès refusé à cette classe.")


# ---------------------------------------------------------------------------
# Périmètre « matières » (saisie et lecture des notes du corps enseignant)
# ---------------------------------------------------------------------------
def matieres_autorisees(db: Session, user: User) -> set[str] | None:
    """Matières que le compte peut écrire.

    None = toutes (Administrateur) ; set() = aucune (tout autre rôle, et
    Professeur sans fiche enseignant liée).
    """
    role = role_courant(db, user)
    if role == ROLE_ADMIN:
        return None
    if role != ROLE_PROF:
        return set()
    if not user.enseignant_id:
        return set()
    ens = sd.get_enseignant(db, user.enseignant_id)
    if ens is None or not ens.matiere_id:
        return set()
    return {ens.matiere_id}


def matieres_notes_lecture(db: Session, user: User) -> set[str] | None:
    """Matières dont les notes sont lisibles.

    None = toutes (Administrateur, Élève, Parent — la restriction porte alors
    sur les **élèves** via `ids_eleves_notes`) ; Professeur = sa matière ;
    Surveillant = aucune.
    """
    role = role_courant(db, user)
    if role == ROLE_PROF:
        return matieres_autorisees(db, user)
    if role == ROLE_SURVEILLANT:
        return set()
    return None


def exiger_acces_notes(db: Session, user: User) -> None:
    """Interdit l'accès aux notes à tout rôle hors corps enseignant."""
    role = role_courant(db, user)
    if role not in ROLES_NOTES:
        raise HTTPException(status_code=403, detail="Accès réservé au corps enseignant.")
    if role == ROLE_PROF and user.enseignant_id is None:
        raise HTTPException(status_code=403, detail="Aucune fiche enseignant liée.")


# ---------------------------------------------------------------------------
# Phase 2 — Capacités de l'interface
# ---------------------------------------------------------------------------
# Même problème que la Phase 1, mais côté navigateur : `js/ui.js` décidait
# seul quelles pages montrer, à partir de `sessionStorage` (que l'utilisateur
# peut modifier) et *sans restriction par défaut* — toute page sans clé
# `roles` était donc visible par tout le monde. Un Parent voyait ainsi les
# entrées « Élèves », « Notes », « Rémunérations », etc.
#
# Ici, les listes ci-dessous sont la **seule** source de vérité : elles
# reproduisent exactement les `require_roles(...)` des routeurs. Le front ne
# fait plus que les afficher (principe : *le serveur autorise, le navigateur
# présente*).
#
# ⚠️ Toute nouvelle page du menu ou tout nouvel écran d'action doit être
# ajouté ICI en même temps que sa route, sinon il n'apparaîtra jamais.

#: Clés de pages telles que déclarées dans `js/ui.js` (tableau PAGES).
PAGES_PAR_ROLE: dict[str, tuple[str, ...]] = {
    ROLE_ADMIN: (
        "dashboard",
        "students",
        "teachers",
        "classes",
        "subjects",
        "grades",
        "report-cards",
        "timetable",
        "payments",
        "paie",
        "announcements",
        "utilisateurs",
        "settings",
    ),
    ROLE_PROF: (
        "dashboard",
        "students",
        "teachers",
        "classes",
        "subjects",
        "grades",
        "report-cards",
        "timetable",
        "mes-seances",
        "ma-paie",
        "announcements",
        "settings",
    ),
    # Vie scolaire : élèves, classes et emplois du temps ; ni notes ni argent.
    # `GET /notes` et `/classes/{id}/bulletins` refusent ce rôle → pas de page.
    ROLE_SURVEILLANT: (
        "dashboard",
        "students",
        "teachers",
        "classes",
        "subjects",
        "timetable",
        "announcements",
        "settings",
    ),
    # Élève et parent : uniquement leur propre dossier (le serveur réduit déjà
    # toutes les listes à leur périmètre).
    ROLE_ELEVE: (
        "dashboard",
        "students",
        "grades",
        "report-cards",
        "timetable",
        "payments",
        "announcements",
        "settings",
    ),
    ROLE_PARENT: (
        "dashboard",
        "students",
        "grades",
        "report-cards",
        "timetable",
        "payments",
        "announcements",
        "settings",
    ),
}

#: Écrans accessibles mais hors menu (liens internes). `students` couvre
#: `pages/student-profile.html`, qui n'a pas d'entrée de menu propre.
PAGES_HORS_MENU: tuple[str, ...] = ("student-profile",)

#: Rôle inconnu, rattachement suspendu ou compte sans membre : rien.
#: On garde le tableau de bord (chiffres à zéro) et les paramètres pour que
#: le compte puisse au moins se déconnecter ou régulariser sa situation.
PAGES_MINIMALES: tuple[str, ...] = ("dashboard", "settings")

#: Capacités d'écriture. Elles correspondent une à une aux `require_roles`
#: des routeurs de modification.
OPERATIONS_PAR_ROLE: dict[str, tuple[str, ...]] = {
    ROLE_ADMIN: (
        "ecole.ecrire",
        "eleves.ecrire",
        "enseignants.ecrire",
        "classes.ecrire",
        "matieres.ecrire",
        "annonces.ecrire",
        "membres.ecrire",
        "notes.ecrire",
        "presences.ecrire",
        "finance.ecrire",
        "paie.ecrire",
    ),
    ROLE_PROF: (
        "notes.ecrire",
        "presences.ecrire",
        "seances.ecrire",
    ),
    ROLE_SURVEILLANT: ("presences.ecrire",),
    ROLE_ELEVE: (),
    ROLE_PARENT: (),
}

#: Nature de la vue « élèves » telle que la reçoit le compte. Sert au front
#: pour adapter ses libellés (« Élèves » → « Mes enfants ») et masquer les
#: filtres qui n'auraient aucun sens. Le serveur la calcule à partir du même
#: périmètre que les données, elle ne peut donc pas mentir.
PORTEE_TOUS = "tous"
PORTEE_PERIMETRE = "perimetre"
PORTEE_AUCUN = "aucun"


def pages_autorisees(db: Session, user: User) -> tuple[str, ...]:
    """Clés de pages autorisées pour le rôle effectif de l'établissement."""
    return PAGES_PAR_ROLE.get(role_courant(db, user), PAGES_MINIMALES)


def operations_autorisees(db: Session, user: User) -> tuple[str, ...]:
    """Opérations d'écriture autorisées (liste vide si aucune)."""
    return OPERATIONS_PAR_ROLE.get(role_courant(db, user), ())


def portee_eleves(db: Session, user: User) -> str:
    """« tous », « perimetre » ou « aucun » — calculé sur le périmètre réel."""
    ids = ids_eleves_autorises(db, user)
    if ids is None:
        return PORTEE_TOUS
    return PORTEE_PERIMETRE if ids else PORTEE_AUCUN


def capacites(db: Session, user: User) -> dict:
    """Capacités complètes du compte, consommées par `js/ui.js`.

    Le navigateur n'a plus à interpréter un rôle : il applique ce dictionnaire.
    """
    return {
        "role": role_courant(db, user),
        "pages": list(pages_autorisees(db, user)),
        "operations": list(operations_autorisees(db, user)),
        "portee": portee_eleves(db, user),
    }
