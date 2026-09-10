"""Route — état complet pour le front (bootstrap `GET /api/v1/etat`).

Renvoie, pour tout utilisateur connecté, un instantané cohérent de la base
SQLite (mêmes formes JSON que le front `js/data.js`) afin que les pages
affichent les **données réelles de l'API** sans réécriture page par page.

NB : mode « console de gestion » de la démonstration — l'instantané contient
l'ensemble des données du seed pour tout rôle connecté. Les permissions fines
(élève = sa fiche, parent = ses enfants, écritures admin, etc.) restent
appliquées par les endpoints métier existants (testés par pytest).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import (
    Annonce,
    Classe,
    Ecole,
    Eleve,
    Enseignant,
    Matiere,
    Note,
    Paiement,
    Presence,
    User,
)
from app.routers.paiements import _paiement_out
from app.services import sd
from app.services.sd import CLASSES_ORDER, LIB_PRESENCE

router = APIRouter(prefix="/api/v1", tags=["état complet"])


@router.get("/etat", summary="État complet de la base (bootstrap du front)")
def etat_complet(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict:
    sid = sd.sid_ecole(db)

    # ----------------------------------------------------------- École
    ecole = db.scalar(select(Ecole).where(Ecole.id == sid).limit(1))
    ecole_out: dict = {}
    if ecole is not None:
        ecole_out = {
            "nom": ecole.nom,
            "sigle": ecole.sigle,
            "slogan": ecole.slogan,
            "annee": ecole.annee,
            "devise": ecole.devise,
            "telephone": ecole.telephone,
            "email": ecole.email,
            "adresse": ecole.adresse,
            "version": ecole.version,
        }

    # --------------------------------------------------------- Classes
    classes = db.scalars(
        select(Classe).where(Classe.school_id == sid)
    ).all()
    classes = sorted(
        classes,
        key=lambda c: CLASSES_ORDER.index(c.id) if c.id in CLASSES_ORDER else 999,
    )
    classes_out = [sd.classe_to_dict(db, c, effectif=True) for c in classes]

    # -------------------------------------------------------- Matières
    matieres = db.scalars(
        select(Matiere).where(Matiere.school_id == sid).order_by(Matiere.id)
    ).all()
    matieres_out = [sd.matiere_to_dict(m) for m in matieres]

    # ------------------------------------------------------ Enseignants
    enseignants = db.scalars(
        select(Enseignant).where(Enseignant.school_id == sid).order_by(Enseignant.id)
    ).all()
    enseignants_out = [sd.enseignant_to_dict(e) for e in enseignants]

    # ----------------------------------------------------------- Élèves
    eleves = db.scalars(
        select(Eleve).where(Eleve.school_id == sid).order_by(Eleve.id)
    ).all()
    eleves_out = [sd.eleve_to_dict(e) for e in eleves]

    # ------------------------------------------------------------ Notes
    notes = db.execute(
        select(Note)
        .where(Note.school_id == sid)
        .order_by(Note.eleve_id, Note.matiere_id)
    ).scalars().all()
    notes_out = [
        {
            "id": f"N{n.id}",
            "eleveId": n.eleve_id,
            "nom": n.eleve.nom,
            "prenom": n.eleve.prenom,
            "classeId": n.eleve.classe_id,
            "matiereId": n.matiere_id,
            "eval": n.eval,
            "note": n.note,
        }
        for n in notes
    ]

    # -------------------------------------------------------- Présences
    presences = db.execute(
        select(Presence)
        .where(Presence.school_id == sid)
        .order_by(Presence.eleve_id, Presence.date)
    ).scalars().all()
    presences_out = [
        {
            "eleveId": p.eleve_id,
            "date": p.date.isoformat(),
            "statut": p.statut,
            "libelle": LIB_PRESENCE.get(p.statut, p.statut),
        }
        for p in presences
    ]

    # --------------------------------------------------------- Paiements
    paiements = db.scalars(
        select(Paiement).where(Paiement.school_id == sid).order_by(Paiement.eleve_id)
    ).all()
    paiements_out = [_paiement_out(db, p) for p in paiements]

    # --------------------------------------------------------- Annonces
    annonces = db.scalars(
        select(Annonce).where(Annonce.school_id == sid).order_by(Annonce.date)
    ).all()
    annonces_out = [sd.annonce_to_dict(a) for a in annonces]

    return {
        "ecole": ecole_out,
        "classes": classes_out,
        "matieres": matieres_out,
        "enseignants": enseignants_out,
        "eleves": eleves_out,
        "notes": notes_out,
        "presences": presences_out,
        "paiements": paiements_out,
        "annonces": annonces_out,
    }
