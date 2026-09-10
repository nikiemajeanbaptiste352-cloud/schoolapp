"""Routes — espace enseignant & paie.

Deux familles d'endpoints sur le même router (préfixe /api/v1) :

- ``/mon-espace/*``  : l'enseignant signe son cahier de présence (séances de
  cours réellement données) et consulte ses fiches de paie. Accès réservé au
  rôle Professeur avec une fiche enseignant liée.
- ``/paie/*``        : la direction fixe les barèmes, consulte le cahier du
  mois, génère les fiches de paie et les marque payées. Accès administrateur.

Rémunération : taux horaire (FCFA) × heures de cours données dans le mois.
La génération d'une fiche « gèle » les heures et le taux (instantané) ; une
fiche payée ne peut plus être modifiée (ni séance supprimée sur le mois).
"""

from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import ROLE_ADMIN, ROLE_PROF, get_current_user, require_roles
from app.database import get_db
from app.models import Classe, Ecole, Enseignant, EnseignantTaux, FichePaie, Matiere, Seance, User
from app.schemas import MoisIn, SeanceIn, StatutFicheIn, TauxIn
from app.services import sd

router = APIRouter(prefix="/api/v1", tags=["espace enseignant & paie"])

_HEURE_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_STATUTS_FICHE = ("en_attente", "payee")


def _maintenant_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _mois_courant() -> str:
    return date.today().strftime("%Y-%m")


def _valider_mois(mois: str | None) -> str:
    mois = mois or _mois_courant()
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", mois):
        raise HTTPException(status_code=400, detail="Mois invalide (format AAAA-MM).")
    return mois


def _bornes_mois(mois: str) -> tuple[date, date]:
    annee, m = int(mois[:4]), int(mois[5:7])
    debut = date(annee, m, 1)
    fin = date(annee, m, calendar.monthrange(annee, m)[1])
    return debut, fin


def _parse_heure(valeur: str) -> int | None:
    """Minutes depuis minuit, ou None si invalide."""
    if not _HEURE_RE.fullmatch(valeur or ""):
        return None
    hh, mm = int(valeur[:2]), int(valeur[3:5])
    return hh * 60 + mm


def _heures_seance(debut: str, fin: str) -> float | None:
    """Heures (décimales) d'une séance, ou None si horaires invalides."""
    a, b = _parse_heure(debut), _parse_heure(fin)
    if a is None or b is None or b <= a:
        return None
    return round((b - a) / 60.0, 2)


def _devise(db: Session) -> str:
    ecole = db.scalar(select(Ecole).where(Ecole.id == sd.sid_ecole(db)).limit(1))
    return (ecole.devise if ecole and ecole.devise else "FCFA")


def _enseignant_du_prof(db: Session, user: User) -> Enseignant:
    """Fiche Enseignant liée au compte Professeur courant (sinon 403/404)."""
    if user.role != ROLE_PROF or not user.enseignant_id:
        raise HTTPException(
            status_code=403,
            detail="Votre compte n'est pas lié à une fiche enseignant. Contactez l'administration.",
        )
    ens = sd.get_enseignant(db, user.enseignant_id)
    if ens is None:
        raise HTTPException(status_code=404, detail="Fiche enseignant introuvable.")
    return ens


def _seance_out(db: Session, s: Seance) -> dict:
    ens = sd.get_enseignant(db, s.enseignant_id)
    classe = sd.get_classe(db, s.classe_id)
    matiere = sd.get_matiere(db, s.matiere_id) if s.matiere_id else None
    heures = _heures_seance(s.heure_debut, s.heure_fin)
    return {
        "id": s.id,
        "enseignantId": s.enseignant_id,
        "enseignantNom": f"{ens.prenom} {ens.nom}" if ens else s.enseignant_id,
        "date": s.date.isoformat(),
        "classeId": s.classe_id,
        "classeNom": classe.nom if classe else s.classe_id,
        "matiereId": s.matiere_id,
        "matiereNom": matiere.nom if matiere else "—",
        "heureDebut": s.heure_debut,
        "heureFin": s.heure_fin,
        "heures": heures if heures is not None else 0,
        "creeLe": s.cree_le.strftime("%Y-%m-%d %H:%M") if s.cree_le else "",
    }


def _fiche_out(db: Session, f: FichePaie) -> dict:
    ens = sd.get_enseignant(db, f.enseignant_id)
    matiere = sd.get_matiere(db, ens.matiere_id) if ens and ens.matiere_id else None
    return {
        "id": f.id,
        "enseignantId": f.enseignant_id,
        "enseignantNom": f"{ens.prenom} {ens.nom}" if ens else f.enseignant_id,
        "matiereNom": matiere.nom if matiere else "—",
        "mois": f.mois,
        "heures": f.heures,
        "tauxHoraire": f.taux_horaire,
        "brut": f.brut,
        "statut": f.statut,
        "creeLe": f.cree_le.strftime("%Y-%m-%d %H:%M") if f.cree_le else "",
        "payeeLe": f.payee_le.strftime("%Y-%m-%d %H:%M") if f.payee_le else None,
    }


def _verrouille_mois(db: Session, enseignant_id: str, mois: str) -> FichePaie | None:
    """Fiche payée existante sur ce mois (verrouille les séances), sinon None."""
    return db.scalar(
        select(FichePaie).where(
            FichePaie.school_id == sd.sid_ecole(db),
            FichePaie.enseignant_id == enseignant_id,
            FichePaie.mois == mois,
        )
    )


# ======================================================================
# Espace enseignant (Professeur lié à sa fiche)
# ======================================================================
@router.get("/mon-espace/profil", summary="Profil enseignant pour son espace")
def profil_enseignant(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(ROLE_PROF)),
) -> dict:
    ens = _enseignant_du_prof(db, user)
    taux = sd.get_taux(db, ens.id)
    matiere = sd.get_matiere(db, ens.matiere_id) if ens.matiere_id else None
    return {
        "enseignant": {
            "id": ens.id,
            "nom": ens.nom,
            "prenom": ens.prenom,
            "email": ens.email,
            "tel": ens.tel,
            "matiereId": ens.matiere_id,
            "matiereNom": matiere.nom if matiere else "—",
            "statut": ens.statut,
            "classes": [
                {"id": c.id, "nom": c.nom, "cycle": c.cycle}
                for c in sorted(ens.classes, key=lambda c: c.id)
            ],
        },
        "tauxHoraire": taux.taux_horaire if taux else 0,
        "devise": _devise(db),
        "mois": _mois_courant(),
    }


@router.get("/mon-espace/seances", summary="Mes séances signées (mois)")
def mes_seances(
    mois: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(ROLE_PROF)),
) -> dict:
    ens = _enseignant_du_prof(db, user)
    mois = _valider_mois(mois)
    debut, fin = _bornes_mois(mois)
    rows = db.scalars(
        select(Seance)
        .where(
            Seance.school_id == ens.school_id,
            Seance.enseignant_id == ens.id,
            Seance.date >= debut,
            Seance.date <= fin,
        )
        .order_by(Seance.date, Seance.heure_debut)
    ).all()
    seances = [_seance_out(db, s) for s in rows]
    heures = round(sum(s["heures"] for s in seances), 2)
    return {
        "mois": mois,
        "seances": seances,
        "nbSeances": len(seances),
        "heuresTotal": heures,
    }


@router.post(
    "/mon-espace/seances",
    status_code=status.HTTP_201_CREATED,
    summary="Signer une séance dans le cahier de présence",
)
def signer_seance(
    body: SeanceIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(ROLE_PROF)),
) -> dict:
    ens = _enseignant_du_prof(db, user)

    # Date
    try:
        jour = date.fromisoformat((body.date or "").strip())
    except ValueError:
        raise HTTPException(status_code=400, detail="Date invalide (format AAAA-MM-JJ).")
    if jour > date.today():
        raise HTTPException(status_code=400, detail="Impossible de signer une séance dans le futur.")

    # Classe : l'enseignant ne signe que dans ses classes affectées
    classe = sd.get_classe(db, body.classe_id)
    if classe is None:
        raise HTTPException(status_code=400, detail="Classe inconnue.")
    if classe not in ens.classes:
        raise HTTPException(
            status_code=400,
            detail="Vous n'enseignez pas dans cette classe. Classe non affectée à votre fiche.",
        )

    # Matière : celle de sa fiche (ou aucune si la fiche n'a pas de matière)
    matiere_id = (body.matiere_id or "").strip() or None
    if matiere_id is None:
        matiere_id = ens.matiere_id
    if matiere_id is not None:
        matiere = sd.get_matiere(db, matiere_id)
        if matiere is None:
            raise HTTPException(status_code=400, detail="Matière inconnue.")
        if matiere_id != ens.matiere_id:
            raise HTTPException(
                status_code=400,
                detail="Vous ne pouvez signer que la matière rattachée à votre fiche.",
            )

    # Horaires
    heures = _heures_seance(body.heure_debut, body.heure_fin)
    if heures is None:
        raise HTTPException(
            status_code=400,
            detail="Horaires invalides : format HH:MM et heure de fin après le début.",
        )

    # Mois déjà réglé : le cahier du mois est clos (fiche payée)
    fiche_payee = _verrouille_mois(db, ens.id, jour.strftime("%Y-%m"))
    if fiche_payee is not None and fiche_payee.statut == "payee":
        raise HTTPException(
            status_code=400,
            detail="Ce mois a déjà été réglé (fiche payée). Seule la direction peut contre-passer la fiche.",
        )

    seance = Seance(
        school_id=ens.school_id,
        enseignant_id=ens.id,
        date=jour,
        classe_id=classe.id,
        matiere_id=matiere_id,
        heure_debut=body.heure_debut,
        heure_fin=body.heure_fin,
    )
    db.add(seance)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Cette séance est déjà signée (même date, classe et heure de début).",
        )
    db.refresh(seance)
    return _seance_out(db, seance)


@router.delete("/mon-espace/seances/{seance_id}", summary="Annuler une séance signée")
def annuler_seance(
    seance_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Supprime une signature. Le Professeur ne supprime que la sienne ;
    l'administrateur peut corriger n'importe quelle séance."""
    seance = db.get(Seance, seance_id)
    if seance is None or seance.school_id != sd.sid_ecole(db):
        raise HTTPException(status_code=404, detail="Séance introuvable.")
    if user.role == ROLE_PROF:
        if user.enseignant_id != seance.enseignant_id:
            raise HTTPException(status_code=403, detail="Cette séance ne vous appartient pas.")
    elif user.role != ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="Droits insuffisants.")

    mois = seance.date.strftime("%Y-%m")
    fiche = _verrouille_mois(db, seance.enseignant_id, mois)
    if fiche is not None:
        raise HTTPException(
            status_code=400,
            detail="Ce mois est déjà clôturé dans une fiche de paie. Corrigez d'abord la fiche.",
        )
    db.delete(seance)
    db.commit()
    return {"message": f"Séance {seance_id} supprimée."}


@router.get("/mon-espace/fiches", summary="Mes fiches de paie")
def mes_fiches(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(ROLE_PROF)),
) -> dict:
    ens = _enseignant_du_prof(db, user)
    rows = db.scalars(
        select(FichePaie)
        .where(
            FichePaie.school_id == ens.school_id,
            FichePaie.enseignant_id == ens.id,
        )
        .order_by(FichePaie.mois.desc())
    ).all()
    return {"fiches": [_fiche_out(db, f) for f in rows], "devise": _devise(db)}


# ======================================================================
# Direction (Administrateur)
# ======================================================================
@router.get("/paie/enseignants", summary="Enseignants et barèmes (direction)")
def enseignants_paie(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_roles(ROLE_ADMIN)),
) -> dict:
    sid = sd.sid_ecole(db)
    ens_list = db.scalars(
        select(Enseignant).where(Enseignant.school_id == sid).order_by(Enseignant.id)
    ).all()
    result = []
    for ens in ens_list:
        taux = sd.get_taux(db, ens.id)
        matiere = sd.get_matiere(db, ens.matiere_id) if ens.matiere_id else None
        result.append(
            {
                "id": ens.id,
                "nom": ens.nom,
                "prenom": ens.prenom,
                "matiereId": ens.matiere_id,
                "matiereNom": matiere.nom if matiere else "—",
                "statut": ens.statut,
                "nbClasses": len(ens.classes),
                "tauxHoraire": taux.taux_horaire if taux else 0,
            }
        )
    return {"enseignants": result, "devise": _devise(db)}


@router.put(
    "/paie/enseignants/{enseignant_id}/taux",
    summary="Fixer le taux horaire d'un enseignant",
)
def maj_taux(
    enseignant_id: str,
    body: TauxIn,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_roles(ROLE_ADMIN)),
) -> dict:
    ens = sd.get_enseignant(db, enseignant_id)
    if ens is None:
        raise HTTPException(status_code=404, detail="Enseignant introuvable.")
    taux = body.taux_horaire
    if taux is None or taux < 0:
        raise HTTPException(status_code=400, detail="Taux horaire invalide (≥ 0).")
    ligne = sd.get_taux(db, enseignant_id)
    if ligne is None:
        ligne = EnseignantTaux(
            school_id=ens.school_id, enseignant_id=enseignant_id, taux_horaire=taux
        )
        db.add(ligne)
    else:
        ligne.taux_horaire = taux
        ligne.maj_le = _maintenant_utc()
    db.commit()
    return {"enseignantId": enseignant_id, "tauxHoraire": taux}


@router.get("/paie/seances", summary="Cahier de signatures du mois (direction)")
def cahier_seances(
    mois: str | None = Query(default=None),
    enseignant_id: str | None = Query(default=None),
    classe_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_roles(ROLE_ADMIN)),
) -> dict:
    mois = _valider_mois(mois)
    debut, fin = _bornes_mois(mois)
    sid = sd.sid_ecole(db)
    stmt = (
        select(Seance)
        .where(
            Seance.school_id == sid,
            Seance.date >= debut,
            Seance.date <= fin,
        )
        .order_by(Seance.date, Seance.heure_debut, Seance.enseignant_id)
    )
    if enseignant_id:
        stmt = stmt.where(Seance.enseignant_id == enseignant_id)
    if classe_id:
        stmt = stmt.where(Seance.classe_id == classe_id)
    rows = db.scalars(stmt).all()
    seances = [_seance_out(db, s) for s in rows]
    heures = round(sum(s["heures"] for s in seances), 2)
    return {
        "mois": mois,
        "seances": seances,
        "nbSeances": len(seances),
        "heuresTotal": heures,
    }


@router.get("/paie/recap", summary="Récapitulatif du mois par enseignant (direction)")
def recap_paie(
    mois: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_roles(ROLE_ADMIN)),
) -> dict:
    mois = _valider_mois(mois)
    debut, fin = _bornes_mois(mois)
    sid = sd.sid_ecole(db)

    seances = db.scalars(
        select(Seance).where(
            Seance.school_id == sid,
            Seance.date >= debut,
            Seance.date <= fin,
        )
    ).all()
    par_ens: dict[str, list[Seance]] = {}
    for s in seances:
        par_ens.setdefault(s.enseignant_id, []).append(s)

    fiches = db.scalars(
        select(FichePaie).where(FichePaie.school_id == sid, FichePaie.mois == mois)
    ).all()
    fiche_par_ens = {f.enseignant_id: f for f in fiches}

    # Enseignants concernés : ayant signé au moins une séance OU déjà dotés d'une fiche
    concernes = sorted(set(par_ens) | set(fiche_par_ens))
    lignes = []
    for eid in concernes:
        ens = sd.get_enseignant(db, eid)
        if ens is None:
            continue
        matiere = sd.get_matiere(db, ens.matiere_id) if ens.matiere_id else None
        taux_row = sd.get_taux(db, eid)
        taux = taux_row.taux_horaire if taux_row else 0
        seances_ens = par_ens.get(eid, [])
        heures = round(sum(_heures_seance(s.heure_debut, s.heure_fin) or 0 for s in seances_ens), 2)
        brut = int(heures * taux + 0.5)
        fiche = fiche_par_ens.get(eid)
        lignes.append(
            {
                "enseignantId": eid,
                "nom": ens.nom,
                "prenom": ens.prenom,
                "matiereNom": matiere.nom if matiere else "—",
                "statutEnseignant": ens.statut,
                "tauxHoraire": taux,
                "nbSeances": len(seances_ens),
                "heures": heures,
                "brut": brut,
                "ficheId": fiche.id if fiche else None,
                "statutFiche": fiche.statut if fiche else None,
                "moisCloture": fiche is not None,
            }
        )
    return {"mois": mois, "lignes": lignes, "devise": _devise(db)}


@router.post("/paie/fiches", summary="Générer les fiches de paie du mois")
def generer_fiches(
    body: MoisIn,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_roles(ROLE_ADMIN)),
) -> dict:
    mois = _valider_mois(body.mois)
    debut, fin = _bornes_mois(mois)
    sid = sd.sid_ecole(db)

    seances = db.scalars(
        select(Seance).where(
            Seance.school_id == sid,
            Seance.date >= debut,
            Seance.date <= fin,
        )
    ).all()
    par_ens: dict[str, list[Seance]] = {}
    for s in seances:
        par_ens.setdefault(s.enseignant_id, []).append(s)

    fiches = db.scalars(
        select(FichePaie).where(FichePaie.school_id == sid, FichePaie.mois == mois)
    ).all()
    fiche_par_ens = {f.enseignant_id: f for f in fiches}

    creees, maj, payees_ignorees, sans_taux = 0, 0, 0, []
    for eid, liste in sorted(par_ens.items()):
        ens = sd.get_enseignant(db, eid)
        taux_row = sd.get_taux(db, eid)
        taux = taux_row.taux_horaire if taux_row else 0
        if ens is None:
            continue
        heures = round(sum(_heures_seance(s.heure_debut, s.heure_fin) or 0 for s in liste), 2)
        brut = int(heures * taux + 0.5)

        fiche = fiche_par_ens.get(eid)
        if fiche is not None:
            if fiche.statut == "payee":
                payees_ignorees += 1
                continue
            fiche.heures = heures
            fiche.taux_horaire = taux
            fiche.brut = brut
            maj += 1
            continue
        if taux <= 0:
            sans_taux.append(eid)
        db.add(
            FichePaie(
                school_id=sid,
                enseignant_id=eid,
                mois=mois,
                heures=heures,
                taux_horaire=taux,
                brut=brut,
            )
        )
        creees += 1
    db.commit()
    return {
        "mois": mois,
        "creees": creees,
        "maj": maj,
        "payeesIgnorees": payees_ignorees,
        "sansTaux": sans_taux,
    }


@router.put("/paie/fiches/{fiche_id}/statut", summary="Marquer une fiche payée / en attente")
def maj_statut_fiche(
    fiche_id: int,
    body: StatutFicheIn,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_roles(ROLE_ADMIN)),
) -> dict:
    fiche = db.get(FichePaie, fiche_id)
    if fiche is None or fiche.school_id != sd.sid_ecole(db):
        raise HTTPException(status_code=404, detail="Fiche de paie introuvable.")
    statut = (body.statut or "").strip()
    if statut not in _STATUTS_FICHE:
        raise HTTPException(status_code=400, detail="Statut invalide (en_attente / payee).")
    fiche.statut = statut
    fiche.payee_le = _maintenant_utc() if statut == "payee" else None
    db.commit()
    db.refresh(fiche)
    return _fiche_out(db, fiche)


@router.delete("/paie/fiches/{fiche_id}", summary="Supprimer une fiche en attente")
def supprimer_fiche(
    fiche_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_roles(ROLE_ADMIN)),
) -> dict:
    fiche = db.get(FichePaie, fiche_id)
    if fiche is None or fiche.school_id != sd.sid_ecole(db):
        raise HTTPException(status_code=404, detail="Fiche de paie introuvable.")
    if fiche.statut == "payee":
        raise HTTPException(
            status_code=400,
            detail="Une fiche payée ne peut pas être supprimée (contre-passation interdite).",
        )
    db.delete(fiche)
    db.commit()
    return {"message": f"Fiche du mois {fiche.mois} supprimée."}
