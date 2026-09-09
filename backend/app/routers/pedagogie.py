"""Routes — pédagogie : notes, statistiques et bulletins de classe.

Professeurs : accès limité aux notes des matières qu'ils enseignent.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import ROLE_ADMIN, ROLE_PROF, get_current_user, require_roles
from app.database import get_db
from app.models import Eleve, Note, User
from app.services import sd

router = APIRouter(prefix="/api/v1", tags=["pédagogie"])


def _matieres_autorisees(db: Session, user: User) -> set[str] | None:
    """None = toutes les matières ; sinon ensemble des ids autorisés."""
    if user.role == ROLE_ADMIN:
        return None
    if user.role == ROLE_PROF and user.enseignant_id:
        ens = sd.get_enseignant(db, user.enseignant_id)
        if ens and ens.matiere_id:
            return {ens.matiere_id}
        return set()
    return set()


def _verifier_acces_notes(db: Session, user: User) -> None:
    if user.role not in (ROLE_ADMIN, ROLE_PROF):
        raise HTTPException(status_code=403, detail="Accès réservé au corps enseignant.")
    if user.role == ROLE_PROF and user.enseignant_id is None:
        raise HTTPException(status_code=403, detail="Aucune fiche enseignant liée.")


# ---------------------------------------------------------------------------
# Liste brute des notes (filtres classe / matière / évaluation)
# ---------------------------------------------------------------------------
@router.get("/notes", summary="Notes brutes (filtres classe, matière, évaluation)")
def liste_notes(
    classe: str | None = Query(default=None),
    matiere: str | None = Query(default=None),
    eval: str | None = Query(default=None, alias="evaluation"),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(ROLE_ADMIN, ROLE_PROF)),
) -> dict:
    _verifier_acces_notes(db, user)
    mats = _matieres_autorisees(db, user)

    stmt = select(Note, Eleve).join(Eleve, Note.eleve_id == Eleve.id)
    if classe:
        stmt = stmt.where(Eleve.classe_id == classe)
    if matiere:
        stmt = stmt.where(Note.matiere_id == matiere)
    if mats is not None:
        stmt = stmt.where(Note.matiere_id.in_(mats))
    if eval:
        stmt = stmt.where(Note.eval == eval)

    lignes = [
        {
            "id": _note_id(n, e),
            "eleveId": e.id,
            "nom": e.nom,
            "prenom": e.prenom,
            "classeId": e.classe_id,
            "matiereId": n.matiere_id,
            "eval": n.eval,
            "note": n.note,
        }
        for n, e in db.execute(stmt).all()
    ]
    return {"notes": lignes, "total": len(lignes)}


def _note_id(note: Note, eleve: Eleve) -> str:
    n = int(eleve.id.replace("EL", ""))
    mat_n = int(note.matiere_id.replace("S", ""))
    ei = sd.EVALS.index(note.eval) if note.eval in sd.EVALS else 0
    return f"N{n * 100 + mat_n * 10 + ei}"


# ---------------------------------------------------------------------------
# Enregistrement en masse (upsert) — bouton « Enregistrer » du front
# ---------------------------------------------------------------------------
@router.put("/notes", summary="Enregistrer des notes en masse (upsert)")
def enregistrer_notes(
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(ROLE_ADMIN, ROLE_PROF)),
) -> dict:
    _verifier_acces_notes(db, user)
    mats = _matieres_autorisees(db, user)
    lignes = payload.get("notes", [])
    if not isinstance(lignes, list) or not lignes:
        raise HTTPException(status_code=400, detail="Champ 'notes' attendu (liste non vide).")

    nb_crees = nb_maj = 0
    for ligne in lignes:
        eleve_id = ligne["eleveId"]
        matiere_id = ligne["matiereId"]
        eval_nom = ligne["eval"]
        note = float(ligne["note"])

        if not (0 <= note <= 20):
            raise HTTPException(status_code=400, detail=f"Note hors bornes (0–20) : {note}")
        if mats is not None and matiere_id not in mats:
            raise HTTPException(status_code=403, detail="Matière non autorisée pour ce professeur.")
        if sd.get_eleve(db, eleve_id) is None:
            raise HTTPException(status_code=404, detail=f"Élève {eleve_id} introuvable.")

        existant = db.scalar(
            select(Note).where(
                Note.eleve_id == eleve_id,
                Note.matiere_id == matiere_id,
                Note.eval == eval_nom,
            )
        )
        if existant:
            existant.note = note
            nb_maj += 1
        else:
            db.add(Note(eleve_id=eleve_id, matiere_id=matiere_id, eval=eval_nom, note=note))
            nb_crees += 1

    db.commit()
    return {"message": f"{nb_crees} note(s) créée(s), {nb_maj} mise(s) à jour."}


@router.delete("/notes", summary="Supprimer une note (admin/professeur)")
def supprimer_note(
    eleveId: str = Query(..., description="Identifiant de l'élève (ex : EL001)"),
    matiereId: str = Query(..., description="Identifiant de la matière (ex : S1)"),
    eval: str = Query(..., description="Évaluation (Devoir 1 / Devoir 2 / Composition)"),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(ROLE_ADMIN, ROLE_PROF)),
) -> dict:
    """Suppression d'une note précise (case vide à l'écran de saisie)."""
    _verifier_acces_notes(db, user)
    mats = _matieres_autorisees(db, user)
    if mats is not None and matiereId not in mats:
        raise HTTPException(status_code=403, detail="Matière non autorisée pour ce professeur.")
    if sd.get_eleve(db, eleveId) is None:
        raise HTTPException(status_code=404, detail=f"Élève {eleveId} introuvable.")

    note = db.scalar(
        select(Note).where(
            Note.eleve_id == eleveId,
            Note.matiere_id == matiereId,
            Note.eval == eval,
        )
    )
    if note is None:
        raise HTTPException(status_code=404, detail="Note introuvable pour ce triplet.")
    db.delete(note)
    db.commit()
    return {"message": "Note supprimée."}


# ---------------------------------------------------------------------------
# Statistiques d'une évaluation pour une classe (grille de notes)
# ---------------------------------------------------------------------------
@router.get("/notes/stats", summary="Stats d'une évaluation (moyenne, max, min, compteur)")
def stats_evaluation(
    classe: str = Query(...),
    matiere: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    eleves = sd.eleves_de_classe(db, classe)
    mat_ids = [m.id for m in sd.matieres_de_classe(db, classe)]

    resultat = []
    for eleve in eleves:
        moy = sd.moyennes_eleve(db, eleve.id)
        par = {p["matiereId"]: p for p in moy["parMatiere"]}
        ligne = {
            "eleveId": eleve.id,
            "nom": eleve.nom,
            "prenom": eleve.prenom,
            "moyenne": moy["generale"],
            "notes": {mid: (par.get(mid, {}).get("moyenne")) for mid in mat_ids},
        }
        resultat.append(ligne)

    return {"classe": classe, "matieres": mat_ids, "eleves": resultat}


# ---------------------------------------------------------------------------
# Bulletin de classe (liste de fiches par élève)
# ---------------------------------------------------------------------------
@router.get("/classes/{classe_id}/bulletins", summary="Bulletins de la classe (1er trimestre)")
def bulletins_classe(
    classe_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    cls = sd.get_classe(db, classe_id)
    if cls is None:
        raise HTTPException(status_code=404, detail="Classe introuvable.")

    eleves = sd.eleves_de_classe(db, classe_id)
    lignes = []
    for eleve in eleves:
        moy = sd.moyennes_eleve(db, eleve.id)
        rang = sd.rang_eleve(db, eleve.id)
        app = sd.appreciation(moy["generale"])
        lignes.append({
            "eleveId": eleve.id,
            "nom": eleve.nom,
            "prenom": eleve.prenom,
            "sexe": eleve.sexe,
            "moyenne": moy["generale"],
            "mention": app["mention"],
            "appreciation": app["texte"],
            "rang": rang,
            "parMatiere": moy["parMatiere"],
        })
    return {
        "classe": sd.classe_to_dict(db, cls),
        "periode": "1er trimestre",
        "annee": "2026 – 2027",
        "bulletins": lignes,
    }
