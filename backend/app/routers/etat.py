"""Route — état complet pour le front (bootstrap `GET /api/v1/etat`).

Renvoie un instantané cohérent de la base (mêmes formes JSON que le front
`js/data.js`) afin que les pages affichent les **données réelles de l'API**
sans réécriture page par page.

Phase 1 — cloisonnement : la **forme** de la réponse ne change pas (mêmes clés
de premier niveau, mêmes clés internes), mais son **contenu** est réduit au
périmètre du rôle effectif dans l'établissement courant
(`services/perimetre.py`) :

- Administrateur : établissement entier ;
- Professeur     : tous les élèves, notes limitées à sa matière, aucune finance ;
- Surveillant    : élèves et présences, ni notes ni finance ;
- Élève          : sa fiche, ses notes, ses présences, son paiement ;
- Parent         : les mêmes données, limitées à ses enfants.

Avant cette phase, l'instantané contenait l'ensemble de l'établissement pour
tout rôle connecté : un parent fraîchement inscrit recevait les données de
tous les autres élèves.
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
    Enseignant,
    Matiere,
    Note,
    Paiement,
    Presence,
    User,
)
from app.routers.paiements import _paiement_out
from app.services import perimetre, sd
from app.services.sd import CLASSES_ORDER, LIB_PRESENCE

router = APIRouter(prefix="/api/v1", tags=["état complet"])


@router.get("/etat", summary="État complet de la base (bootstrap du front)")
def etat_complet(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
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
    # Les coordonnées (téléphone / email) ne sont servies qu'au personnel
    # encadrant : un élève ou un parent n'a pas à recevoir l'annuaire complet.
    annuaire = perimetre.peut_voir_annuaire(db, user)
    enseignants = db.scalars(
        select(Enseignant).where(Enseignant.school_id == sid).order_by(Enseignant.id)
    ).all()
    enseignants_out = []
    for enseignant in enseignants:
        d = sd.enseignant_to_dict(enseignant)
        if not annuaire:
            d["tel"] = ""
            d["email"] = ""
        enseignants_out.append(d)

    # ----------------------------------------------------------- Élèves
    # Périmètre calculé côté serveur à partir du rôle effectif : un compte
    # Élève / Parent ne reçoit que sa fiche ou celles de ses enfants.
    eleves = perimetre.eleves_visibles(db, user)
    ids_eleves = perimetre.ids_eleves_autorises(db, user)
    eleves_out = []
    for eleve in eleves:
        d = sd.eleve_to_dict(eleve)
        if ids_eleves is not None:
            # Vue réduite : le navigateur n'a plus la classe entière, il ne
            # peut donc plus calculer le rang. On le fournit côté serveur.
            d["rang"] = sd.rang_eleve(db, eleve.id)
        eleves_out.append(d)

    # ------------------------------------------------------------ Notes
    ids_notes = perimetre.ids_eleves_notes(db, user)
    matieres_notes = perimetre.matieres_notes_lecture(db, user)
    notes_out: list[dict] = []
    if ids_notes != set() and matieres_notes != set():
        stmt_notes = select(Note).where(Note.school_id == sid)
        if ids_notes is not None:
            stmt_notes = stmt_notes.where(Note.eleve_id.in_(ids_notes))
        if matieres_notes is not None:
            stmt_notes = stmt_notes.where(Note.matiere_id.in_(matieres_notes))
        notes = db.execute(
            stmt_notes.order_by(Note.eleve_id, Note.matiere_id)
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
    ids_presences = perimetre.ids_eleves_presences(db, user)
    presences_out: list[dict] = []
    if ids_presences != set():
        stmt_presences = select(Presence).where(Presence.school_id == sid)
        if ids_presences is not None:
            stmt_presences = stmt_presences.where(Presence.eleve_id.in_(ids_presences))
        presences = db.execute(
            stmt_presences.order_by(Presence.eleve_id, Presence.date)
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
    # Professeur et Surveillant : aucun accès à la finance (liste vide).
    ids_finance = perimetre.ids_eleves_finance(db, user)
    paiements_out: list[dict] = []
    if ids_finance != set():
        stmt_paiements = select(Paiement).where(Paiement.school_id == sid)
        if ids_finance is not None:
            stmt_paiements = stmt_paiements.where(Paiement.eleve_id.in_(ids_finance))
        paiements = db.scalars(
            stmt_paiements.order_by(Paiement.eleve_id)
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
