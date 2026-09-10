"""Routes — référentiel : classes, matières, enseignants.

Classes et matières étaient en lecture seule (programme canonique fourni par
le seed) ; elles sont désormais gérables par l'administrateur (création /
modification / suppression) afin de pouvoir bootstraper une base vide depuis
l'interface. Les enseignants sont également gérables par l'administrateur.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.auth import ROLE_ADMIN, require_roles
from app.database import get_db
from app.models import (
    Classe,
    Eleve,
    Enseignant,
    Matiere,
    Note,
    classe_matiere,
    enseignant_classe,
)
from app.services import sd

router = APIRouter(prefix="/api/v1", tags=["référentiel"])


# ---------------------------------------------------------------------------
# Classes
# ---------------------------------------------------------------------------
@router.get("/classes", summary="Liste des classes (avec effectif)")
def liste_classes(db: Session = Depends(get_db)) -> dict:
    sid = sd.sid_ecole(db)
    classes = db.execute(
        select(Classe).where(Classe.school_id == sid)
    ).scalars().all()
    # Ordre stable identique à data.js, puis les codes hors programme (ex. 6C)
    # ajoutés depuis l'interface, triés par code.
    par_id = {c.id: c for c in classes}
    connus = [par_id[cid] for cid in sd.CLASSES_ORDER if cid in par_id]
    inconnus = sorted(
        (c for cid, c in par_id.items() if cid not in sd.CLASSES_ORDER),
        key=lambda c: c.id,
    )
    return {"classes": [sd.classe_to_dict(db, c) for c in connus + inconnus]}


@router.get("/classes/{classe_id}", summary="Détail d'une classe")
def detail_classe(classe_id: str, db: Session = Depends(get_db)) -> dict:
    cls = sd.get_classe(db, classe_id)
    if cls is None:
        raise HTTPException(status_code=404, detail="Classe introuvable.")

    principal = cls.principal
    matieres = sd.matieres_de_classe(db, classe_id)
    # Professeurs intervenant dans cette classe
    profs = db.execute(
        select(Enseignant).join(Enseignant.classes).where(
            Classe.school_id == sd.sid_ecole(db), Classe.id == classe_id
        )
    ).scalars().all()

    return {
        **sd.classe_to_dict(db, cls),
        "principalNom": f"{principal.prenom} {principal.nom}" if principal else None,
        "matieres": [sd.matiere_to_dict(m) for m in matieres],
        "enseignants": [sd.enseignant_to_dict(p) for p in profs],
        "eleves": [sd.eleve_to_dict(e) for e in sd.eleves_de_classe(db, classe_id)],
    }


@router.get("/classes/{classe_id}/emploi-du-temps", summary="Emploi du temps d'une classe")
def emploi_du_temps(classe_id: str, db: Session = Depends(get_db)) -> dict:
    cls = sd.get_classe(db, classe_id)
    if cls is None:
        raise HTTPException(status_code=404, detail="Classe introuvable.")
    return {
        "classe": sd.classe_to_dict(db, cls, effectif=False),
        "jours": sd.JOURS,
        "creneaux": sd.CRENEAUX,
        "grille": sd.emploi_du_temps(db, classe_id),
    }


# ---------------------------------------------------------------------------
# Matières
# ---------------------------------------------------------------------------
@router.get("/matieres", summary="Liste des matières")
def liste_matieres(db: Session = Depends(get_db)) -> dict:
    sid = sd.sid_ecole(db)
    matieres = db.execute(
        select(Matiere).where(Matiere.school_id == sid)
    ).scalars().all()
    par_id = {m.id: m for m in matieres}

    def cle_num(m):
        # Trie numérique sur la partie entière (S9 < S10)
        num = re.sub(r"\D", "", m.id)
        return (int(num) if num else 0, m.id)

    connues = [par_id[mid] for mid in sd.MATIERES_ORDER if mid in par_id]
    inconnues = sorted(
        (m for mid, m in par_id.items() if mid not in sd.MATIERES_ORDER),
        key=cle_num,
    )
    return {"matieres": [sd.matiere_to_dict(m) for m in connues + inconnues]}


# ---------------------------------------------------------------------------
# Enseignants
# ---------------------------------------------------------------------------
@router.get("/enseignants", summary="Liste des enseignants")
def liste_enseignants(db: Session = Depends(get_db)) -> dict:
    sid = sd.sid_ecole(db)
    ens = db.execute(
        select(Enseignant).where(Enseignant.school_id == sid).order_by(Enseignant.id)
    ).scalars().all()
    return {"enseignants": [sd.enseignant_to_dict(e) for e in ens]}


@router.get("/enseignants/{enseignant_id}", summary="Détail d'un enseignant")
def detail_enseignant(enseignant_id: str, db: Session = Depends(get_db)) -> dict:
    ens = sd.get_enseignant(db, enseignant_id)
    if ens is None:
        raise HTTPException(status_code=404, detail="Enseignant introuvable.")
    return sd.enseignant_to_dict(ens)


# ---------------------------------------------------------------------------
# Enseignants — gestion (admin) : création / modification / suppression
# ---------------------------------------------------------------------------
def _nouvel_id_enseignant(db: Session, sid: int) -> str:
    max_id = db.scalar(
        select(func.max(Enseignant.id)).where(Enseignant.school_id == sid)
    )  # ex : "T012"
    num = int(re.sub(r"\D", "", max_id or "T000")) + 1
    return f"T{num:03d}"


def _valider_enseignant(db: Session, payload: dict) -> None:
    if not (payload.get("nom") or "").strip() or not (payload.get("prenom") or "").strip():
        raise HTTPException(status_code=400, detail="Le nom et le prénom sont obligatoires.")
    matiere_id = payload.get("matiere")
    if matiere_id and sd.get_matiere(db, matiere_id) is None:
        raise HTTPException(status_code=400, detail="Matière inconnue.")
    for cid in payload.get("classes") or []:
        if sd.get_classe(db, cid) is None:
            raise HTTPException(status_code=400, detail=f"Classe inconnue : {cid}")


def _classes_pour(db: Session, ids: list[str]) -> list[Classe]:
    return [c for cid in ids if (c := sd.get_classe(db, cid)) is not None]


@router.post("/enseignants", summary="Créer un enseignant (admin)")
def creer_enseignant(
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_roles(ROLE_ADMIN)),
) -> dict:
    _valider_enseignant(db, payload)
    sid = sd.sid_ecole(db)
    ens = Enseignant(
        school_id=sid,
        id=_nouvel_id_enseignant(db, sid),
        nom=(payload.get("nom") or "").strip(),
        prenom=(payload.get("prenom") or "").strip(),
        sexe=payload.get("sexe", "M"),
        tel=payload.get("tel") or "—",
        email=payload.get("email") or "—",
        matiere_id=payload.get("matiere") or None,
        statut=payload.get("statut", "Actif"),
    )
    ens.classes = _classes_pour(db, payload.get("classes") or [])
    db.add(ens)
    db.commit()
    db.refresh(ens)
    return sd.enseignant_to_dict(ens)


@router.put("/enseignants/{enseignant_id}", summary="Modifier un enseignant (admin)")
def modifier_enseignant(
    enseignant_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_roles(ROLE_ADMIN)),
) -> dict:
    ens = sd.get_enseignant(db, enseignant_id)
    if ens is None:
        raise HTTPException(status_code=404, detail="Enseignant introuvable.")
    _valider_enseignant(db, payload)

    for champ in ("nom", "prenom", "sexe", "tel", "email", "statut"):
        if champ in payload:
            setattr(ens, champ, payload[champ])
    if "matiere" in payload:
        ens.matiere_id = payload.get("matiere") or None
    if "classes" in payload:
        ens.classes = _classes_pour(db, payload.get("classes") or [])

    db.commit()
    db.refresh(ens)
    return sd.enseignant_to_dict(ens)


@router.delete("/enseignants/{enseignant_id}", summary="Supprimer un enseignant (admin)")
def supprimer_enseignant(
    enseignant_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_roles(ROLE_ADMIN)),
) -> dict:
    ens = sd.get_enseignant(db, enseignant_id)
    if ens is None:
        raise HTTPException(status_code=404, detail="Enseignant introuvable.")
    # Délie la fonction de professeur principal sur les classes concernées.
    # UPDATE SQL direct (avant suppression) : nuller via l'ORM déclencherait un
    # null-out de la PK composée (school_id + principal_id) — interdit.
    sid = sd.sid_ecole(db)
    db.execute(
        update(Classe)
        .where(Classe.school_id == sid, Classe.principal_id == enseignant_id)
        .values(principal_id=None)
    )
    db.delete(ens)
    db.commit()
    return {"message": f"Enseignant {enseignant_id} supprimé."}


# ---------------------------------------------------------------------------
# Classes — gestion (admin) : création / modification / suppression
# ---------------------------------------------------------------------------
_CYCLES = ("Collège", "Lycée")


def _inferer_cycle(code: str) -> str:
    """Cycle par défaut selon le code (2nde/1ère/Terminale → Lycée)."""
    return "Lycée" if code[:1] in ("1", "2", "T") else "Collège"


def _principal_valide(db: Session, principal: str | None) -> str | None:
    """Renvoie l'id du professeur principal si valide (ou None)."""
    pid = (principal or "").strip() or None
    if pid is not None and sd.get_enseignant(db, pid) is None:
        raise HTTPException(status_code=400, detail=f"Enseignant inconnu : {pid}")
    return pid


@router.post("/classes", summary="Créer une classe (admin)")
def creer_classe(
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_roles(ROLE_ADMIN)),
) -> dict:
    code = (str(payload.get("id") or "")).strip().upper()
    if not code:
        raise HTTPException(status_code=400, detail="Le code de la classe est obligatoire (ex. 6C, TA).")
    if not re.fullmatch(r"[A-Z0-9]{1,6}", code):
        raise HTTPException(status_code=400, detail="Code invalide : lettres et chiffres uniquement (ex. 6C, TA).")
    if sd.get_classe(db, code) is not None:
        raise HTTPException(status_code=409, detail=f"Une classe porte déjà le code {code}.")
    cycle = payload.get("cycle") or _inferer_cycle(code)
    if cycle not in _CYCLES:
        raise HTTPException(status_code=400, detail="Cycle invalide : Collège ou Lycée.")
    nom = (payload.get("nom") or "").strip() or code
    principal = _principal_valide(db, payload.get("principal"))
    salle = (str(payload.get("salle") or "")).strip() or "—"

    cls = Classe(
        school_id=sd.sid_ecole(db),
        id=code, nom=nom, cycle=cycle, salle=salle, principal_id=principal,
    )
    db.add(cls)
    db.commit()
    db.refresh(cls)
    return sd.classe_to_dict(db, cls)


@router.put("/classes/{classe_id}", summary="Modifier une classe (admin)")
def modifier_classe(
    classe_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_roles(ROLE_ADMIN)),
) -> dict:
    cls = sd.get_classe(db, classe_id)
    if cls is None:
        raise HTTPException(status_code=404, detail="Classe introuvable.")

    if "nom" in payload:
        nom = (payload.get("nom") or "").strip()
        if not nom:
            raise HTTPException(status_code=400, detail="Le nom de la classe ne peut pas être vide.")
        cls.nom = nom
    if "cycle" in payload:
        if payload["cycle"] not in _CYCLES:
            raise HTTPException(status_code=400, detail="Cycle invalide : Collège ou Lycée.")
        cls.cycle = payload["cycle"]
    if "salle" in payload:
        cls.salle = (str(payload.get("salle") or "")).strip() or "—"
    if "principal" in payload:
        cls.principal_id = _principal_valide(db, payload.get("principal"))

    db.commit()
    db.refresh(cls)
    return sd.classe_to_dict(db, cls)


@router.delete("/classes/{classe_id}", summary="Supprimer une classe (admin)")
def supprimer_classe(
    classe_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_roles(ROLE_ADMIN)),
) -> dict:
    cls = sd.get_classe(db, classe_id)
    if cls is None:
        raise HTTPException(status_code=404, detail="Classe introuvable.")
    sid = sd.sid_ecole(db)
    nb = db.scalar(
        select(func.count(Eleve.id)).where(
            Eleve.school_id == sid, Eleve.classe_id == classe_id
        )
    ) or 0
    if nb:
        raise HTTPException(
            status_code=409,
            detail=f"Suppression impossible : {nb} élève(s) encore inscrit(s) dans cette classe.",
        )
    # Retire les liens matière↔classe et enseignant↔classe avant suppression
    db.execute(
        classe_matiere.delete().where(
            classe_matiere.c.school_id == sid, classe_matiere.c.classe_id == classe_id
        )
    )
    db.execute(
        enseignant_classe.delete().where(
            enseignant_classe.c.school_id == sid,
            enseignant_classe.c.classe_id == classe_id,
        )
    )
    db.delete(cls)
    db.commit()
    return {"message": f"Classe {classe_id} supprimée."}


# ---------------------------------------------------------------------------
# Matières — gestion (admin) : création / modification / suppression
# ---------------------------------------------------------------------------
def _nouvel_id_matiere(db: Session, sid: int) -> str:
    max_id = db.scalar(
        select(func.max(Matiere.id)).where(Matiere.school_id == sid)
    )  # ex : "S8"
    num = int(re.sub(r"\D", "", max_id or "S0")) + 1
    return f"S{num}"


def _coef_valide(coef) -> int:
    try:
        valeur = int(coef)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Le coefficient doit être un nombre entier.")
    if valeur < 1 or valeur > 20:
        raise HTTPException(status_code=400, detail="Le coefficient doit être compris entre 1 et 20.")
    return valeur


@router.post("/matieres", summary="Créer une matière (admin)")
def creer_matiere(
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_roles(ROLE_ADMIN)),
) -> dict:
    nom = (payload.get("nom") or "").strip()
    if not nom:
        raise HTTPException(status_code=400, detail="Le nom de la matière est obligatoire.")
    coef = _coef_valide(payload.get("coef", 1))

    sid = sd.sid_ecole(db)
    mat = Matiere(
        school_id=sid,
        id=_nouvel_id_matiere(db, sid),
        nom=nom,
        coef=coef,
        icone=payload.get("icone") or "📘",
        couleur=payload.get("couleur") or "blue",
    )
    db.add(mat)
    db.commit()
    db.refresh(mat)
    return sd.matiere_to_dict(mat)


@router.put("/matieres/{matiere_id}", summary="Modifier une matière (admin)")
def modifier_matiere(
    matiere_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_roles(ROLE_ADMIN)),
) -> dict:
    mat = sd.get_matiere(db, matiere_id)
    if mat is None:
        raise HTTPException(status_code=404, detail="Matière introuvable.")

    if "nom" in payload:
        nom = (payload.get("nom") or "").strip()
        if not nom:
            raise HTTPException(status_code=400, detail="Le nom de la matière ne peut pas être vide.")
        mat.nom = nom
    if "coef" in payload:
        mat.coef = _coef_valide(payload["coef"])
    if "icone" in payload and payload["icone"]:
        mat.icone = payload["icone"]
    if "couleur" in payload and payload["couleur"]:
        mat.couleur = payload["couleur"]

    db.commit()
    db.refresh(mat)
    return sd.matiere_to_dict(mat)


@router.delete("/matieres/{matiere_id}", summary="Supprimer une matière (admin)")
def supprimer_matiere(
    matiere_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_roles(ROLE_ADMIN)),
) -> dict:
    mat = sd.get_matiere(db, matiere_id)
    if mat is None:
        raise HTTPException(status_code=404, detail="Matière introuvable.")
    sid = sd.sid_ecole(db)
    nb_notes = db.scalar(
        select(func.count(Note.id)).where(
            Note.school_id == sid, Note.matiere_id == matiere_id
        )
    ) or 0
    if nb_notes:
        raise HTTPException(
            status_code=409,
            detail=f"Suppression impossible : {nb_notes} note(s) existent dans cette matière.",
        )
    # Délie les enseignants rattachés (matiere_id nullable) et les programmes de classes.
    # UPDATE SQL direct (avant suppression) : nuller via l'ORM déclencherait un
    # null-out de la PK composée (school_id + matiere_id) — interdit.
    db.execute(
        update(Enseignant)
        .where(Enseignant.school_id == sid, Enseignant.matiere_id == matiere_id)
        .values(matiere_id=None)
    )
    db.execute(
        classe_matiere.delete().where(
            classe_matiere.c.school_id == sid, classe_matiere.c.matiere_id == matiere_id
        )
    )
    db.delete(mat)
    db.commit()
    return {"message": f"Matière {matiere_id} supprimée."}
