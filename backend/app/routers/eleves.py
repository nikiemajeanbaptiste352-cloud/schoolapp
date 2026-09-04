"""Routes — élèves : liste, fiche détaillée, création/modification/suppression.

Périmètre par rôle :
- Administrateur / Professeur : tous les élèves ;
- Élève : uniquement sa propre fiche ;
- Parent : uniquement ses enfants.
"""

from __future__ import annotations

import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.auth import (
    ROLE_ADMIN,
    ROLE_ELEVE,
    ROLE_PARENT,
    ROLE_PROF,
    get_current_user,
    require_roles,
)
from app.database import get_db
from app.models import Eleve, Parent, User
from app.services import sd

router = APIRouter(prefix="/api/v1/eleves", tags=["élèves"])


def _ids_autorises(db: Session, user: User) -> set[str] | None:
    """Retourne l'ensemble des ids accessibles, ou None si aucun filtre (tous)."""
    if user.role in (ROLE_ADMIN, ROLE_PROF):
        return None
    if user.role == ROLE_ELEVE and user.eleve_id:
        return {user.eleve_id}
    if user.role == ROLE_PARENT and user.parent_id:
        parent = db.get(Parent, user.parent_id)
        return {e.id for e in parent.enfants} if parent else set()
    return set()


def _eleve_trouve(db: Session, eleve_id: str, user: User) -> Eleve:
    eleve = sd.get_eleve(db, eleve_id)
    if eleve is None:
        raise HTTPException(status_code=404, detail="Élève introuvable.")
    ids = _ids_autorises(db, user)
    if ids is not None and eleve.id not in ids:
        raise HTTPException(status_code=403, detail="Accès refusé à cette fiche élève.")
    return eleve


# ---------------------------------------------------------------------------
# Liste
# ---------------------------------------------------------------------------
@router.get("/", summary="Liste des élèves (filtres : classe, recherche)")
def liste_eleves(
    classe: str | None = Query(default=None, description="Filtrer par classe (ex : 3A)"),
    q: str | None = Query(default=None, description="Recherche nom/prénom/matricule"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    ids = _ids_autorises(db, user)
    stmt = select(Eleve)
    if ids is not None:
        stmt = stmt.where(Eleve.id.in_(ids))
    if classe:
        stmt = stmt.where(Eleve.classe_id == classe)
    if q:
        terme = f"%{q.strip()}%"
        stmt = stmt.where(or_(Eleve.nom.ilike(terme), Eleve.prenom.ilike(terme), Eleve.id.ilike(terme)))

    eleves = db.execute(stmt.order_by(Eleve.id)).scalars().all()
    return {"eleves": [_fiche_liste(db, e) for e in eleves], "total": len(eleves)}


def _fiche_liste(db: Session, eleve: Eleve) -> dict:
    return {
        **sd.eleve_to_dict(eleve),
        "classeNom": eleve.classe.nom if eleve.classe else eleve.classe_id,
        "tauxPresence": sd.taux_presence(db, eleve.id),
    }


# ---------------------------------------------------------------------------
# Fiche détaillée
# ---------------------------------------------------------------------------
@router.get("/{eleve_id}", summary="Fiche détaillée d'un élève")
def fiche_eleve(
    eleve_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    eleve = _eleve_trouve(db, eleve_id, user)

    moyennes = sd.moyennes_eleve(db, eleve.id)
    rang = sd.rang_eleve(db, eleve.id)
    app = sd.appreciation(moyennes["generale"])

    return _construire_fiche(db, eleve, moyennes, rang, app)


def _construire_fiche(
    db: Session, eleve: Eleve, moyennes: dict, rang: dict | None, app: dict
) -> dict:
    cls = eleve.classe
    pres = db.execute(
        select(sd.Presence).where(sd.Presence.eleve_id == eleve.id).order_by(sd.Presence.date)
    ).scalars().all()
    nb_abs = sum(1 for p in pres if p.statut == "A")
    nb_ret = sum(1 for p in pres if p.statut == "R")

    paiement = sd.paiement_eleve(db, eleve.id)
    paiement_out = None
    if paiement is not None:
        versements = sorted(paiement.versements, key=lambda v: v.date)
        paye = sum(v.montant for v in versements)
        paiement_out = {
            "motif": paiement.motif,
            "total": paiement.total,
            "paye": paye,
            "restant": paiement.total - paye,
            "statut": sd.statut_paiement(paiement),
            "versements": [
                {"montant": v.montant, "date": v.date.isoformat(), "mode": v.mode}
                for v in versements
            ],
        }

    return {
        **sd.eleve_to_dict(eleve),
        "classeNom": cls.nom if cls else eleve.classe_id,
        "cycle": cls.cycle if cls else None,
        "principal": f"{cls.principal.prenom} {cls.principal.nom}" if cls and cls.principal else None,
        "rang": rang,
        "presence": {
            "taux": sd.taux_presence(db, eleve.id),
            "absences": nb_abs,
            "retards": nb_ret,
            "total": len(pres),
        },
        "paiement": paiement_out,
        "resultats": {
            **moyennes,
            "mention": app["mention"],
            "appreciation": app["texte"],
        },
        "bulletins": [
            {
                "periode": "1er trimestre",
                "annee": "2026 – 2027",
                "moyenne": moyennes["generale"],
                "mention": app["mention"],
                "appreciation": app["texte"],
                "rang": rang,
                "parMatiere": moyennes["parMatiere"],
            }
        ],
    }


# ---------------------------------------------------------------------------
# Création / modification / suppression
# ---------------------------------------------------------------------------
def _nouvel_id(db: Session) -> str:
    max_id = db.scalar(select(func.max(Eleve.id)))  # ex : "EL015"
    num = int(re.sub(r"\D", "", max_id or "EL000")) + 1
    return f"EL{num:03d}"


@router.post("/", summary="Créer un élève (admin)")
def creer_eleve(
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_roles(ROLE_ADMIN)),
) -> dict:
    classe_id = payload["classe"]
    if sd.get_classe(db, classe_id) is None:
        raise HTTPException(status_code=400, detail="Classe inconnue.")

    parent_data = payload.get("parent")
    parent = None
    if parent_data:
        parent = Parent(
            nom=parent_data.get("nom", ""),
            lien=parent_data.get("lien", "Père"),
            tel=parent_data.get("tel", ""),
            email=parent_data.get("email", ""),
            profession=parent_data.get("profession", ""),
            adresse=parent_data.get("adresse", ""),
        )
        db.add(parent)
        db.flush()

    eleve = Eleve(
        id=_nouvel_id(db),
        nom=payload["nom"],
        prenom=payload["prenom"],
        sexe=payload.get("sexe", "M"),
        naissance=date.fromisoformat(payload["naissance"]),
        classe_id=classe_id,
        statut=payload.get("statut", "Actif"),
        inscription=date.fromisoformat(payload.get("inscription", "2026-09-10")),
        parent_id=parent.id if parent else None,
    )
    db.add(eleve)
    db.commit()
    db.refresh(eleve)
    return _fiche_liste(db, eleve)


@router.put("/{eleve_id}", summary="Modifier un élève (admin)")
def modifier_eleve(
    eleve_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_roles(ROLE_ADMIN)),
) -> dict:
    eleve = sd.get_eleve(db, eleve_id)
    if eleve is None:
        raise HTTPException(status_code=404, detail="Élève introuvable.")

    for champ in ("nom", "prenom", "sexe", "statut"):
        if champ in payload:
            setattr(eleve, champ, payload[champ])
    if "naissance" in payload:
        eleve.naissance = date.fromisoformat(payload["naissance"])
    if "classe" in payload:
        if sd.get_classe(db, payload["classe"]) is None:
            raise HTTPException(status_code=400, detail="Classe inconnue.")
        eleve.classe_id = payload["classe"]

    # Mise à jour du parent éventuel
    parent_data = payload.get("parent")
    if parent_data:
        if eleve.parent is None:
            parent = Parent(nom="", lien="Père", tel="", email="", profession="", adresse="")
            db.add(parent)
            db.flush()
            eleve.parent_id = parent.id
        for champ in ("nom", "lien", "tel", "email", "profession", "adresse"):
            if champ in parent_data:
                setattr(eleve.parent, champ, parent_data[champ])

    db.commit()
    db.refresh(eleve)
    return _fiche_liste(db, eleve)


@router.delete("/{eleve_id}", summary="Supprimer un élève (admin)")
def supprimer_eleve(
    eleve_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_roles(ROLE_ADMIN)),
) -> dict:
    eleve = sd.get_eleve(db, eleve_id)
    if eleve is None:
        raise HTTPException(status_code=404, detail="Élève introuvable.")
    db.delete(eleve)
    db.commit()
    return {"message": "Élève supprimé."}
