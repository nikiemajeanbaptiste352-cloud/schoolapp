"""Routes — réseau scolaire interne (Phase 12).

Réseau **privé à l'établissement** : fil général, groupes de travail, forum,
bibliothèque de ressources. Rien ne sort de l'école — toutes les requêtes
filtrent sur `sd.sid_ecole(db)`, la clé de locataire.

Frontière de données (document d'architecture, zone Z2) appliquée ici :

* La lecture est ouverte à **tout membre rattaché et actif** de l'établissement.
* L'écriture (`reseau.ecrire`) est ouverte aux cinq rôles : c'est un réseau
  *scolaire*, élèves et parents y publient autant que le personnel.
* La modération (`reseau.moderer`) appartient à la direction : elle peut
  masquer (sans effacer la trace) ou supprimer n'importe quel contenu, et
  supprimer un groupe.
* L'auteur peut toujours modifier ou supprimer **son** contenu.
* Interdits du document : aucune note, aucun bulletin, aucun paiement, aucune
  absence, aucun élément de discipline, aucune pièce administrative ne peut
  être publié — le schéma ne prévoit d'ailleurs aucun champ pour cela.
* L'identité exposée est un **instantané** (`auteur_nom`, `auteur_role`)
  figé au moment de l'écriture : la modification ultérieure d'un rattachement
  ne réécrit pas l'histoire du fil.

Le périmètre (qui est qui, dans quelle école) n'est jamais recalculé ici :
il appartient à `services/perimetre.py`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.auth import (
    ROLE_ADMIN,
    ROLE_ELEVE,
    ROLE_PARENT,
    ROLE_PROF,
    ROLE_SURVEILLANT,
    get_current_user,
)
from app.database import get_db
from app.models import (
    CommentairePublication,
    Eleve,
    Groupe,
    MembreGroupe,
    Publication,
    ReactionPublication,
    Ressource,
    TYPES_GROUPE,
    TYPES_PUBLICATION,
    User,
    _maintenant_utc,
)
from app.services import perimetre, sd

router = APIRouter(prefix="/api/v1", tags=["réseau scolaire"])

#: Rôles ayant accès au réseau interne. Un rôle inconnu, un rattachement
#: suspendu ou un compte sans membre n'y entre pas.
ROLES_RESEAU = (ROLE_ADMIN, ROLE_PROF, ROLE_SURVEILLANT, ROLE_ELEVE, ROLE_PARENT)

LIBELLES_ROLE = {
    ROLE_ADMIN: "Direction",
    ROLE_PROF: "Professeur",
    ROLE_SURVEILLANT: "Surveillant",
    ROLE_ELEVE: "Élève",
    ROLE_PARENT: "Parent",
}

ROLES_ENCADREMENT = (ROLE_ADMIN, ROLE_PROF, ROLE_SURVEILLANT)

LONGUEUR_MAX_MESSAGE = 4000


# ---------------------------------------------------------------------------
# Garde d'entrée
# ---------------------------------------------------------------------------
def _role(db: Session, user: User) -> str:
    """Rôle effectif de l'établissement courant (jamais `user.role`)."""
    return perimetre.role_courant(db, user)


def _acces_reseau(db: Session, user: User) -> str:
    """Vérifie l'appartenance au réseau ; renvoie le rôle effectif."""
    role = _role(db, user)
    if role not in ROLES_RESEAU:
        raise HTTPException(
            status_code=403,
            detail="Le réseau scolaire est réservé aux membres de l'établissement.",
        )
    return role


def _peut_moderer(db: Session, user: User) -> bool:
    return _role(db, user) == ROLE_ADMIN


def _texte(valeur: object, champ: str, maxi: int, obligatoire: bool = True) -> str:
    """Nettoie un champ texte : type, longueur, vide interdite si requise."""
    if valeur is None:
        if obligatoire:
            raise HTTPException(status_code=400, detail=f"Champ « {champ} » requis.")
        return ""
    if not isinstance(valeur, str):
        raise HTTPException(
            status_code=400, detail=f"Champ « {champ} » : texte attendu."
        )
    propre = valeur.strip()
    if obligatoire and not propre:
        raise HTTPException(status_code=400, detail=f"Champ « {champ} » requis.")
    if len(propre) > maxi:
        raise HTTPException(
            status_code=400,
            detail=f"Champ « {champ} » : {maxi} caractères maximum.",
        )
    return propre


def _entier(valeur: object, champ: str) -> int:
    try:
        return int(valeur)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400, detail=f"Champ « {champ} » : identifiant attendu."
        ) from None


def _nom_auteur(user: User) -> str:
    """Instantané du nom affiché au moment de l'écriture."""
    nom = (user.nom or "").strip()
    return nom or "Membre"


# ---------------------------------------------------------------------------
# Périmètre des groupes
# ---------------------------------------------------------------------------
def _classes_du_compte(db: Session, user: User) -> set[str]:
    """Classes où le compte a au moins un élève rattaché."""
    ids = perimetre.ids_eleves_autorises(db, user)
    if not ids:
        return set()
    return set(
        db.execute(
            select(Eleve.classe_id).where(
                Eleve.school_id == sd.sid_ecole(db), Eleve.id.in_(ids)
            )
        ).scalars()
    )


def _matieres_du_compte(db: Session, user: User) -> set[str]:
    """Matières étudiées par les classes où le compte a un élève."""
    ids: set[str] = set()
    for classe_id in _classes_du_compte(db, user):
        ids |= set(sd.matieres_ids_classe(db, classe_id))
    return ids


def _groupe_ouvert(groupe: Groupe) -> bool:
    """Groupe librement découvrable et rejoignable (club, projet).

    Un club ou un projet n'a pas de liste d'ayants droit connue à l'avance :
    il doit donc être visible de tout le réseau, sinon il ne serait jamais
    rejoignable. Les groupes « classe » et « matière » restent, eux,
    strictement limités à leur population.
    """
    return groupe.type in ("club", "projet")


def _appartenance_implicite(db: Session, user: User, groupe: Groupe) -> bool:
    """Appartenance déduite du rattachement (classe ou matière), sans inscription."""
    if groupe.type == "classe" and groupe.classe_id:
        return groupe.classe_id in _classes_du_compte(db, user)
    if groupe.type == "matiere" and groupe.matiere_id:
        return groupe.matiere_id in _matieres_du_compte(db, user)
    return False


def _groupes_visibles(db: Session, user: User) -> list[Groupe]:
    """Groupes que le compte voit dans le fil.

    Personnel (direction, professeurs, surveillants) : tous les groupes.
    Élève / Parent : les groupes où ils sont explicitement inscrits, les
    groupes adossés à une classe où ils ont un élève, les groupes adossés à
    une matière étudiée par leur classe, et les groupes ouverts (club, projet).
    """
    sid = sd.sid_ecole(db)
    tous = list(
        db.execute(
            select(Groupe).where(Groupe.school_id == sid).order_by(Groupe.nom)
        ).scalars()
    )
    if _role(db, user) in ROLES_ENCADREMENT:
        return tous

    explicites = set(
        db.execute(
            select(MembreGroupe.groupe_id).where(
                MembreGroupe.school_id == sid, MembreGroupe.user_id == user.id
            )
        ).scalars()
    )
    return [
        g
        for g in tous
        if g.id in explicites
        or _groupe_ouvert(g)
        or _appartenance_implicite(db, user, g)
    ]


def _est_membre(db: Session, user: User, groupe: Groupe) -> bool:
    """Appartenance logique : inscription explicite ou rattachement déduit."""
    sid = sd.sid_ecole(db)
    if db.scalar(
        select(MembreGroupe.id).where(
            MembreGroupe.school_id == sid,
            MembreGroupe.groupe_id == groupe.id,
            MembreGroupe.user_id == user.id,
        )
    ):
        return True
    return _appartenance_implicite(db, user, groupe)


def _groupe_ou_404(db: Session, groupe_id: int) -> Groupe:
    g = db.scalar(
        select(Groupe).where(
            Groupe.school_id == sd.sid_ecole(db), Groupe.id == groupe_id
        )
    )
    if g is None:
        # 404 volontaire (et non 403) : ne révèle pas l'existence d'un groupe
        # appartenant à un autre établissement.
        raise HTTPException(status_code=404, detail="Groupe introuvable.")
    return g


# ---------------------------------------------------------------------------
# Sérialisation
# ---------------------------------------------------------------------------
def _dto_groupe(
    db: Session, groupe: Groupe, user: User, membres: int, est_membre: bool
) -> dict:
    classe = sd.get_classe(db, groupe.classe_id) if groupe.classe_id else None
    matiere = sd.get_matiere(db, groupe.matiere_id) if groupe.matiere_id else None
    return {
        "id": groupe.id,
        "nom": groupe.nom,
        "description": groupe.description or "",
        "type": groupe.type,
        "classeId": groupe.classe_id,
        "classeNom": classe.nom if classe is not None else None,
        "matiereId": groupe.matiere_id,
        "matiereNom": matiere.nom if matiere is not None else None,
        "membres": membres,
        "estMembre": est_membre,
        "ouvert": _groupe_ouvert(groupe),
        "estCreateur": groupe.cree_par == user.id,
        "peutSupprimer": _peut_moderer(db, user) or groupe.cree_par == user.id,
        "creeLe": groupe.cree_le.isoformat() if groupe.cree_le else None,
    }


def _dto_commentaire(
    c: CommentairePublication, user: User, est_moderateur: bool
) -> dict:
    return {
        "id": c.id,
        "contenu": c.contenu,
        "auteurId": c.auteur_id,
        "auteurNom": c.auteur_nom,
        "auteurRole": c.auteur_role,
        "auteurRoleLibelle": LIBELLES_ROLE.get(c.auteur_role, c.auteur_role),
        "estAuteur": c.auteur_id == user.id,
        "peutSupprimer": est_moderateur or c.auteur_id == user.id,
        "creeLe": c.cree_le.isoformat() if c.cree_le else None,
    }


def _serialiser_fil(
    db: Session,
    pubs: list[Publication],
    user: User,
    est_moderateur: bool,
    groupes: dict[int, Groupe],
) -> list[dict]:
    """Assemble le fil : auteur, groupe, commentaires et réactions.

    Les commentaires et réactions des publications de la page sont chargés en
    **trois requêtes** au total (et non une par message), pour rester rapide
    même sur un fil de plusieurs centaines de messages.
    """
    if not pubs:
        return []
    sid = sd.sid_ecole(db)
    ids = [p.id for p in pubs]

    commentaires: dict[int, list[CommentairePublication]] = {i: [] for i in ids}
    for c in db.execute(
        select(CommentairePublication)
        .where(
            CommentairePublication.school_id == sid,
            CommentairePublication.publication_id.in_(ids),
        )
        .order_by(CommentairePublication.cree_le, CommentairePublication.id)
    ).scalars():
        if c.masque and not est_moderateur:
            continue
        commentaires.setdefault(c.publication_id, []).append(c)

    compteurs: dict[int, int] = {i: 0 for i in ids}
    mes_reactions: set[int] = set()
    for pid, uid in db.execute(
        select(ReactionPublication.publication_id, ReactionPublication.user_id).where(
            ReactionPublication.school_id == sid,
            ReactionPublication.publication_id.in_(ids),
        )
    ).all():
        compteurs[pid] = compteurs.get(pid, 0) + 1
        if uid == user.id:
            mes_reactions.add(pid)

    resultat: list[dict] = []
    for p in pubs:
        groupe = groupes.get(p.groupe_id) if p.groupe_id else None
        resultat.append(
            {
                "id": p.id,
                "type": p.type,
                "titre": p.titre or "",
                "contenu": p.contenu,
                "groupeId": p.groupe_id,
                "groupeNom": groupe.nom if groupe is not None else None,
                "auteurId": p.auteur_id,
                "auteurNom": p.auteur_nom,
                "auteurRole": p.auteur_role,
                "auteurRoleLibelle": LIBELLES_ROLE.get(p.auteur_role, p.auteur_role),
                "estAuteur": p.auteur_id == user.id,
                "peutModifier": p.auteur_id == user.id,
                "peutSupprimer": est_moderateur or p.auteur_id == user.id,
                "peutModerer": est_moderateur,
                "epingle": bool(p.epingle),
                "masque": bool(p.masque),
                "jaime": p.id in mes_reactions,
                "jaimeCount": compteurs.get(p.id, 0),
                "commentaires": [
                    _dto_commentaire(c, user, est_moderateur)
                    for c in commentaires.get(p.id, [])
                ],
                "creeLe": p.cree_le.isoformat() if p.cree_le else None,
                "majLe": p.maj_le.isoformat() if p.maj_le else None,
            }
        )
    return resultat


# ---------------------------------------------------------------------------
# Fil d'actualité
# ---------------------------------------------------------------------------
@router.get("/reseau/fil", summary="Fil du réseau scolaire (général, groupe, forum)")
def lire_fil(
    groupe: str | None = Query(default=None, description="'general' ou id de groupe"),
    type_: str | None = Query(default=None, alias="type"),
    q: str | None = Query(default=None, description="Recherche plein texte"),
    auteur: str | None = Query(default=None, description="'moi' ou id de compte"),
    limite: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    _acces_reseau(db, user)
    sid = sd.sid_ecole(db)
    est_moderateur = _peut_moderer(db, user)

    visibles = _groupes_visibles(db, user)
    groupes = {g.id: g for g in visibles}

    stmt = select(Publication).where(Publication.school_id == sid)
    if not est_moderateur:
        stmt = stmt.where(Publication.masque.is_(False))

    if groupe:
        if groupe == "general":
            stmt = stmt.where(Publication.groupe_id.is_(None))
        else:
            gid = _entier(groupe, "groupe")
            if gid not in groupes:
                raise HTTPException(status_code=403, detail="Groupe non accessible.")
            stmt = stmt.where(Publication.groupe_id == gid)
    else:
        autorises = or_(
            Publication.groupe_id.is_(None),
            Publication.groupe_id.in_(list(groupes.keys()) or [-1]),
        )
        stmt = stmt.where(autorises)

    if type_:
        if type_ not in TYPES_PUBLICATION:
            raise HTTPException(status_code=400, detail="Type de publication inconnu.")
        stmt = stmt.where(Publication.type == type_)

    if q:
        motif = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Publication.contenu).like(motif),
                func.lower(Publication.titre).like(motif),
            )
        )

    if auteur:
        if auteur == "moi":
            stmt = stmt.where(Publication.auteur_id == user.id)
        else:
            stmt = stmt.where(Publication.auteur_id == _entier(auteur, "auteur"))

    pubs = list(
        db.execute(
            stmt.order_by(
                Publication.epingle.desc(),
                Publication.cree_le.desc(),
                Publication.id.desc(),
            ).limit(limite)
        ).scalars()
    )

    return {
        "publications": _serialiser_fil(db, pubs, user, est_moderateur, groupes),
        "groupes": [
            _dto_groupe(db, g, user, _compter_membres(db, g), _est_membre(db, user, g))
            for g in visibles
        ],
        "peutModerer": est_moderateur,
        "total": len(pubs),
    }


def _compter_membres(db: Session, groupe: Groupe) -> int:
    """Effectif d'un groupe : inscriptions explicites + classe adossée."""
    sid = sd.sid_ecole(db)
    explicites = db.scalar(
        select(func.count())
        .select_from(MembreGroupe)
        .where(
            MembreGroupe.school_id == sid, MembreGroupe.groupe_id == groupe.id
        )
    )
    total = int(explicites or 0)
    if groupe.type == "classe" and groupe.classe_id:
        total += int(
            db.scalar(
                select(func.count())
                .select_from(Eleve)
                .where(
                    Eleve.school_id == sid, Eleve.classe_id == groupe.classe_id
                )
            )
            or 0
        )
    return total


@router.get("/reseau/resume", summary="Compteurs du réseau (tableau de bord)")
def resume(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    _acces_reseau(db, user)
    sid = sd.sid_ecole(db)
    est_moderateur = _peut_moderer(db, user)

    visibles = _groupes_visibles(db, user)
    ids_groupes = [g.id for g in visibles]

    condition_groupe = or_(
        Publication.groupe_id.is_(None), Publication.groupe_id.in_(ids_groupes or [-1])
    )
    stmt = select(func.count()).select_from(Publication).where(
        Publication.school_id == sid, condition_groupe
    )
    if not est_moderateur:
        stmt = stmt.where(Publication.masque.is_(False))

    derniere = db.scalar(
        select(Publication.cree_le)
        .where(Publication.school_id == sid, condition_groupe)
        .order_by(Publication.cree_le.desc())
        .limit(1)
    )
    return {
        "publications": int(db.scalar(stmt) or 0),
        "groupes": len(visibles),
        "ressources": int(
            db.scalar(
                select(func.count())
                .select_from(Ressource)
                .where(Ressource.school_id == sid)
            )
            or 0
        ),
        "dernierePublication": derniere.isoformat() if derniere else None,
    }


# ---------------------------------------------------------------------------
# Publications
# ---------------------------------------------------------------------------
@router.post("/reseau/publications", summary="Publier dans le fil ou dans un groupe")
def publier(
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    role = _acces_reseau(db, user)
    sid = sd.sid_ecole(db)

    contenu = _texte(payload.get("contenu"), "contenu", LONGUEUR_MAX_MESSAGE)
    titre = _texte(payload.get("titre"), "titre", 140, obligatoire=False)
    type_publication = str(payload.get("type") or "publication")
    if type_publication not in TYPES_PUBLICATION:
        raise HTTPException(status_code=400, detail="Type de publication inconnu.")

    groupe_id = payload.get("groupeId")
    groupe = None
    if groupe_id not in (None, "", 0, "0"):
        groupe = _groupe_ou_404(db, _entier(groupe_id, "groupeId"))
        if groupe.id not in {g.id for g in _groupes_visibles(db, user)}:
            raise HTTPException(status_code=403, detail="Groupe non accessible.")

    pub = Publication(
        school_id=sid,
        groupe_id=groupe.id if groupe is not None else None,
        type=type_publication,
        titre=titre,
        contenu=contenu,
        auteur_id=user.id,
        auteur_nom=_nom_auteur(user),
        auteur_role=role,
    )
    db.add(pub)
    db.commit()
    db.refresh(pub)
    univers = {pub.groupe_id: groupe} if groupe is not None else {}
    return {
        "message": "Publication enregistrée.",
        "publication": _serialiser_fil(db, [pub], user, _peut_moderer(db, user), univers)[0],
    }


def _publication_ou_404(db: Session, publication_id: int) -> Publication:
    p = db.scalar(
        select(Publication).where(
            Publication.school_id == sd.sid_ecole(db),
            Publication.id == publication_id,
        )
    )
    if p is None:
        raise HTTPException(status_code=404, detail="Publication introuvable.")
    return p


@router.patch("/reseau/publications/{publication_id}", summary="Modifier / épingler / masquer")
def modifier_publication(
    publication_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    _acces_reseau(db, user)
    est_moderateur = _peut_moderer(db, user)
    pub = _publication_ou_404(db, publication_id)

    if pub.auteur_id != user.id and not est_moderateur:
        raise HTTPException(status_code=403, detail="Seul l'auteur peut modifier ce message.")

    modifie = False
    if "contenu" in payload:
        pub.contenu = _texte(payload.get("contenu"), "contenu", LONGUEUR_MAX_MESSAGE)
        modifie = True
    if "titre" in payload:
        pub.titre = _texte(payload.get("titre"), "titre", 140, obligatoire=False)
        modifie = True

    # Épinglage et masquage : direction uniquement (modération).
    if "epingle" in payload:
        if not est_moderateur:
            raise HTTPException(status_code=403, detail="Réservé à la direction.")
        pub.epingle = bool(payload.get("epingle"))
        modifie = True
    if "masque" in payload:
        if not est_moderateur:
            raise HTTPException(status_code=403, detail="Réservé à la direction.")
        pub.masque = bool(payload.get("masque"))
        modifie = True

    if modifie:
        pub.maj_le = _maintenant_utc()
    db.commit()
    db.refresh(pub)

    groupe = sd.get_groupe(db, pub.groupe_id) if pub.groupe_id else None
    return {
        "message": "Publication mise à jour.",
        "publication": _serialiser_fil(
            db, [pub], user, est_moderateur, {pub.groupe_id: groupe} if groupe else {}
        )[0],
    }


@router.delete("/reseau/publications/{publication_id}", summary="Supprimer une publication")
def supprimer_publication(
    publication_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    _acces_reseau(db, user)
    est_moderateur = _peut_moderer(db, user)
    pub = _publication_ou_404(db, publication_id)
    if pub.auteur_id != user.id and not est_moderateur:
        raise HTTPException(status_code=403, detail="Suppression non autorisée.")

    sid = sd.sid_ecole(db)
    # Suppression explicite des dépendances : portable SQLite / PostgreSQL,
    # sans dépendre d'une cascade déclarée côté base.
    for c in db.execute(
        select(CommentairePublication).where(
            CommentairePublication.school_id == sid,
            CommentairePublication.publication_id == pub.id,
        )
    ).scalars():
        db.delete(c)
    for r in db.execute(
        select(ReactionPublication).where(
            ReactionPublication.school_id == sid,
            ReactionPublication.publication_id == pub.id,
        )
    ).scalars():
        db.delete(r)
    db.delete(pub)
    db.commit()
    return {"message": "Publication supprimée."}


# ---------------------------------------------------------------------------
# Réactions
# ---------------------------------------------------------------------------
@router.post("/reseau/publications/{publication_id}/jaime", summary="Réagir / retirer sa réaction")
def basculer_jaime(
    publication_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    _acces_reseau(db, user)
    sid = sd.sid_ecole(db)
    pub = _publication_ou_404(db, publication_id)

    existante = db.scalar(
        select(ReactionPublication).where(
            ReactionPublication.school_id == sid,
            ReactionPublication.publication_id == pub.id,
            ReactionPublication.user_id == user.id,
        )
    )
    if existante is not None:
        db.delete(existante)
        jaime = False
    else:
        db.add(
            ReactionPublication(
                school_id=sid, publication_id=pub.id, user_id=user.id
            )
        )
        jaime = True
    db.commit()

    total = int(
        db.scalar(
            select(func.count())
            .select_from(ReactionPublication)
            .where(
                ReactionPublication.school_id == sid,
                ReactionPublication.publication_id == pub.id,
            )
        )
        or 0
    )
    return {"jaime": jaime, "jaimeCount": total}


# ---------------------------------------------------------------------------
# Commentaires
# ---------------------------------------------------------------------------
@router.post(
    "/reseau/publications/{publication_id}/commentaires",
    summary="Commenter une publication",
)
def commenter(
    publication_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    role = _acces_reseau(db, user)
    sid = sd.sid_ecole(db)
    pub = _publication_ou_404(db, publication_id)
    contenu = _texte(payload.get("contenu"), "contenu", LONGUEUR_MAX_MESSAGE)

    commentaire = CommentairePublication(
        school_id=sid,
        publication_id=pub.id,
        auteur_id=user.id,
        auteur_nom=_nom_auteur(user),
        auteur_role=role,
        contenu=contenu,
    )
    db.add(commentaire)
    db.commit()
    db.refresh(commentaire)
    return {
        "message": "Commentaire ajouté.",
        "commentaire": _dto_commentaire(commentaire, user, _peut_moderer(db, user)),
    }


@router.delete("/reseau/commentaires/{commentaire_id}", summary="Supprimer un commentaire")
def supprimer_commentaire(
    commentaire_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    _acces_reseau(db, user)
    c = db.scalar(
        select(CommentairePublication).where(
            CommentairePublication.school_id == sd.sid_ecole(db),
            CommentairePublication.id == commentaire_id,
        )
    )
    if c is None:
        raise HTTPException(status_code=404, detail="Commentaire introuvable.")
    if c.auteur_id != user.id and not _peut_moderer(db, user):
        raise HTTPException(status_code=403, detail="Suppression non autorisée.")
    db.delete(c)
    db.commit()
    return {"message": "Commentaire supprimé."}


# ---------------------------------------------------------------------------
# Groupes
# ---------------------------------------------------------------------------
@router.get("/reseau/groupes", summary="Groupes accessibles au compte")
def lister_groupes(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    _acces_reseau(db, user)
    groupes = _groupes_visibles(db, user)
    return {
        "groupes": [
            _dto_groupe(
                db, g, user, _compter_membres(db, g), _est_membre(db, user, g)
            )
            for g in groupes
        ]
    }


@router.post("/reseau/groupes", summary="Créer un groupe de travail")
def creer_groupe(
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    role = _acces_reseau(db, user)
    sid = sd.sid_ecole(db)

    nom = _texte(payload.get("nom"), "nom", 80)
    description = _texte(payload.get("description"), "description", 1000, obligatoire=False)
    type_groupe = str(payload.get("type") or "club")
    if type_groupe not in TYPES_GROUPE:
        raise HTTPException(status_code=400, detail="Type de groupe inconnu.")

    classe_id = payload.get("classeId") or None
    matiere_id = payload.get("matiereId") or None

    # Réciprocité : un rattachement (classe/matière) n'a de sens que sur le type
    # correspondant ; sinon la colonne resterait renseignée à contretemps.
    if classe_id and type_groupe != "classe":
        raise HTTPException(
            status_code=400,
            detail="Un groupe adossé à une classe doit être de type « classe ».",
        )
    if matiere_id and type_groupe != "matiere":
        raise HTTPException(
            status_code=400,
            detail="Un groupe adossé à une matière doit être de type « matière ».",
        )

    # Un groupe structurel (classe ou matière) tient son appartenance du
    # référentiel : sans sa classe ou sa matière, il ne serait visible de
    # personne et resterait un groupe mort. Les deux sont donc obligatoires.
    if type_groupe == "classe":
        if not classe_id:
            raise HTTPException(
                status_code=400, detail="Précisez la classe de ce groupe."
            )
        # Réutilise le périmètre central : un compte ne peut pas adosser un
        # groupe à une classe qu'il n'a pas le droit de voir.
        perimetre.exiger_classe_visible(db, user, str(classe_id))

    if type_groupe == "matiere":
        if role not in ROLES_ENCADREMENT:
            raise HTTPException(
                status_code=403, detail="Réservé au personnel enseignant."
            )
        if not matiere_id:
            raise HTTPException(
                status_code=400, detail="Précisez la matière de ce groupe."
            )
        if sd.get_matiere(db, str(matiere_id)) is None:
            raise HTTPException(status_code=404, detail="Matière introuvable.")

    if db.scalar(
        select(Groupe.id).where(Groupe.school_id == sid, Groupe.nom == nom)
    ):
        raise HTTPException(
            status_code=409, detail="Un groupe porte déjà ce nom dans l'établissement."
        )

    groupe = Groupe(
        school_id=sid,
        nom=nom,
        description=description,
        type=type_groupe,
        classe_id=str(classe_id) if classe_id else None,
        matiere_id=str(matiere_id) if matiere_id else None,
        cree_par=user.id,
    )
    db.add(groupe)
    db.flush()
    db.add(
        MembreGroupe(
            school_id=sid,
            groupe_id=groupe.id,
            user_id=user.id,
            role_membre="responsable",
        )
    )
    db.commit()
    db.refresh(groupe)
    return {
        "message": "Groupe créé.",
        "groupe": _dto_groupe(db, groupe, user, _compter_membres(db, groupe), True),
    }


@router.post("/reseau/groupes/{groupe_id}/rejoindre", summary="Rejoindre un groupe")
def rejoindre_groupe(
    groupe_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    _acces_reseau(db, user)
    sid = sd.sid_ecole(db)
    groupe = _groupe_ou_404(db, groupe_id)
    # Un groupe ouvert se rejoint librement ; les autres exigent d'y être
    # déjà rattaché (classe, matière) ou d'être la direction.
    if (
        not _groupe_ouvert(groupe)
        and not _est_membre(db, user, groupe)
        and not _peut_moderer(db, user)
    ):
        raise HTTPException(status_code=403, detail="Groupe non accessible.")

    if db.scalar(
        select(MembreGroupe.id).where(
            MembreGroupe.school_id == sid,
            MembreGroupe.groupe_id == groupe.id,
            MembreGroupe.user_id == user.id,
        )
    ) is None:
        db.add(
            MembreGroupe(
                school_id=sid, groupe_id=groupe.id, user_id=user.id
            )
        )
        db.commit()
    return {
        "message": "Vous avez rejoint le groupe.",
        "groupe": _dto_groupe(db, groupe, user, _compter_membres(db, groupe), True),
    }


@router.delete("/reseau/groupes/{groupe_id}/quitter", summary="Quitter un groupe")
def quitter_groupe(
    groupe_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    _acces_reseau(db, user)
    sid = sd.sid_ecole(db)
    groupe = _groupe_ou_404(db, groupe_id)
    lien = db.scalar(
        select(MembreGroupe).where(
            MembreGroupe.school_id == sid,
            MembreGroupe.groupe_id == groupe.id,
            MembreGroupe.user_id == user.id,
        )
    )
    if lien is None:
        raise HTTPException(status_code=404, detail="Vous n'êtes pas membre de ce groupe.")
    db.delete(lien)
    db.commit()
    return {"message": "Vous avez quitté le groupe."}


@router.delete("/reseau/groupes/{groupe_id}", summary="Supprimer un groupe (direction)")
def supprimer_groupe(
    groupe_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    _acces_reseau(db, user)
    sid = sd.sid_ecole(db)
    groupe = _groupe_ou_404(db, groupe_id)
    if groupe.cree_par != user.id and not _peut_moderer(db, user):
        raise HTTPException(status_code=403, detail="Suppression non autorisée.")

    # Le groupe disparaît avec ses messages : on supprime explicitement les
    # dépendances pour rester portable (SQLite comme PostgreSQL).
    pubs = list(
        db.execute(
            select(Publication).where(
                Publication.school_id == sid, Publication.groupe_id == groupe.id
            )
        ).scalars()
    )
    ids_pubs = [p.id for p in pubs]
    if ids_pubs:
        for c in db.execute(
            select(CommentairePublication).where(
                CommentairePublication.school_id == sid,
                CommentairePublication.publication_id.in_(ids_pubs),
            )
        ).scalars():
            db.delete(c)
        for r in db.execute(
            select(ReactionPublication).where(
                ReactionPublication.school_id == sid,
                ReactionPublication.publication_id.in_(ids_pubs),
            )
        ).scalars():
            db.delete(r)
    for p in pubs:
        db.delete(p)
    for m in db.execute(
        select(MembreGroupe).where(
            MembreGroupe.school_id == sid, MembreGroupe.groupe_id == groupe.id
        )
    ).scalars():
        db.delete(m)
    db.delete(groupe)
    db.commit()
    return {"message": "Groupe supprimé."}


# ---------------------------------------------------------------------------
# Bibliothèque de ressources
# ---------------------------------------------------------------------------
def _dto_ressource(db: Session, r: Ressource, user: User) -> dict:
    matiere = sd.get_matiere(db, r.matiere_id) if r.matiere_id else None
    return {
        "id": r.id,
        "titre": r.titre,
        "description": r.description or "",
        "type": r.type,
        "url": r.url,
        "matiereId": r.matiere_id,
        "matiereNom": matiere.nom if matiere is not None else None,
        "niveau": r.niveau or "",
        "auteurId": r.auteur_id,
        "auteurNom": r.auteur_nom,
        "estAuteur": r.auteur_id == user.id,
        "peutSupprimer": _peut_moderer(db, user) or r.auteur_id == user.id,
        "creeLe": r.cree_le.isoformat() if r.cree_le else None,
    }


@router.get("/reseau/ressources", summary="Bibliothèque de l'établissement")
def lister_ressources(
    matiere: str | None = Query(default=None),
    q: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    _acces_reseau(db, user)
    sid = sd.sid_ecole(db)
    stmt = select(Ressource).where(Ressource.school_id == sid)
    if matiere:
        stmt = stmt.where(Ressource.matiere_id == matiere)
    if q:
        motif = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Ressource.titre).like(motif),
                func.lower(Ressource.description).like(motif),
            )
        )
    lignes = list(
        db.execute(stmt.order_by(Ressource.cree_le.desc(), Ressource.id.desc())).scalars()
    )
    return {
        "ressources": [_dto_ressource(db, r, user) for r in lignes],
        "total": len(lignes),
    }


@router.post("/reseau/ressources", summary="Partager une ressource")
def creer_ressource(
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    _acces_reseau(db, user)
    sid = sd.sid_ecole(db)

    titre = _texte(payload.get("titre"), "titre", 140)
    url = _texte(payload.get("url"), "url", 1000)
    if not url.lower().startswith(("http://", "https://")):
        raise HTTPException(
            status_code=400, detail="L'adresse doit commencer par http:// ou https://."
        )
    description = _texte(payload.get("description"), "description", 1000, obligatoire=False)
    type_ressource = str(payload.get("type") or "lien")
    if type_ressource not in ("lien", "document", "video", "exercice"):
        raise HTTPException(status_code=400, detail="Type de ressource inconnu.")
    niveau = _texte(payload.get("niveau"), "niveau", 20, obligatoire=False)

    matiere_id = payload.get("matiereId") or None
    if matiere_id and sd.get_matiere(db, str(matiere_id)) is None:
        raise HTTPException(status_code=404, detail="Matière introuvable.")

    ressource = Ressource(
        school_id=sid,
        titre=titre,
        description=description,
        type=type_ressource,
        url=url,
        matiere_id=str(matiere_id) if matiere_id else None,
        niveau=niveau,
        auteur_id=user.id,
        auteur_nom=_nom_auteur(user),
    )
    db.add(ressource)
    db.commit()
    db.refresh(ressource)
    return {
        "message": "Ressource ajoutée à la bibliothèque.",
        "ressource": _dto_ressource(db, ressource, user),
    }


@router.delete("/reseau/ressources/{ressource_id}", summary="Retirer une ressource")
def supprimer_ressource(
    ressource_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    _acces_reseau(db, user)
    r = db.scalar(
        select(Ressource).where(
            Ressource.school_id == sd.sid_ecole(db), Ressource.id == ressource_id
        )
    )
    if r is None:
        raise HTTPException(status_code=404, detail="Ressource introuvable.")
    if r.auteur_id != user.id and not _peut_moderer(db, user):
        raise HTTPException(status_code=403, detail="Suppression non autorisée.")
    db.delete(r)
    db.commit()
    return {"message": "Ressource retirée."}
