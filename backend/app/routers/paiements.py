"""Routes — finance : paiements des élèves et encaissement de versements."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.auth import ROLE_ADMIN, get_current_user, require_roles
from app.database import get_db
from app.models import Eleve, Paiement, User, Versement
from app.services import sd

router = APIRouter(prefix="/api/v1", tags=["finance"])


def _paiement_out(db: Session, paiement: Paiement) -> dict:
    versements = sorted(paiement.versements, key=lambda v: v.date)
    paye = sum(v.montant for v in versements)
    eleve = paiement.eleve
    return {
        "eleveId": paiement.eleve_id,
        "nom": eleve.nom if eleve else "",
        "prenom": eleve.prenom if eleve else "",
        "classe": eleve.classe_id if eleve else None,
        "classeNom": eleve.classe.nom if eleve and eleve.classe else None,
        "motif": paiement.motif,
        "total": paiement.total,
        "paye": paye,
        "restant": paiement.total - paye,
        "statut": sd.statut_paiement(paiement),
        "dernier": (
            {"montant": versements[-1].montant, "date": versements[-1].date.isoformat()}
            if versements else None
        ),
        "versements": [
            {"id": v.id, "montant": v.montant, "date": v.date.isoformat(), "mode": v.mode}
            for v in versements
        ],
    }


@router.get("/paiements", summary="Liste des paiements (filtres classe / statut)")
def liste_paiements(
    classe: str | None = Query(default=None),
    statut: str | None = Query(default=None, description="Payé | Partiellement payé | Impayé"),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict:
    sid = sd.sid_ecole(db)
    stmt = select(Paiement).where(Paiement.school_id == sid)
    if classe:
        stmt = stmt.join(
            Eleve,
            and_(
                Paiement.eleve_id == Eleve.id,
                Paiement.school_id == Eleve.school_id,
            ),
        ).where(Eleve.classe_id == classe)
    paiements = db.execute(stmt).scalars().all()

    resultat = []
    for p in paiements:
        s = sd.statut_paiement(p)
        if statut and s != statut:
            continue
        resultat.append(_paiement_out(db, p))
    return {"paiements": resultat, "total": len(resultat)}


@router.get("/paiements/stats", summary="Synthèse des paiements")
def stats_paiements(db: Session = Depends(get_db)) -> dict:
    sid = sd.sid_ecole(db)
    paiements = db.execute(
        select(Paiement).where(Paiement.school_id == sid)
    ).scalars().all()
    compteurs = {"Payé": 0, "Partiellement payé": 0, "Impayé": 0}
    total_attendu = total_encaisse = 0
    for p in paiements:
        s = sd.statut_paiement(p)
        compteurs[s] = compteurs.get(s, 0) + 1
        total_attendu += p.total
        total_encaisse += sd.montant_paye(p)
    return {
        "compteurs": compteurs,
        "totalAttendu": total_attendu,
        "totalEncaisse": total_encaisse,
        "tauxEncaissement": round(total_encaisse / total_attendu * 100, 1) if total_attendu else 0,
    }


@router.post("/paiements/{eleve_id}/versements", summary="Encaisser un versement (admin)")
def encaisser(
    eleve_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_roles(ROLE_ADMIN)),
) -> dict:
    """Encaissement d'un versement (admin).

    Si l'élève n'a pas encore de dossier côté serveur, un dossier par défaut
    est créé à partir des champs optionnels `motif` / `total` (ou des valeurs
    par défaut cycle Collège 150 000 / Lycée 200 000) : l'interface de
    l'école réelle part d'une base vide, sans dossier pré-existant.
    """
    eleve = sd.get_eleve(db, eleve_id)
    if eleve is None:
        raise HTTPException(status_code=404, detail="Élève introuvable.")
    montant = int(payload["montant"])
    if montant <= 0:
        raise HTTPException(status_code=400, detail="Montant invalide.")

    paiement = sd.paiement_eleve(db, eleve_id)
    if paiement is None:
        cycle = eleve.classe.cycle if eleve.classe else None
        total = int(payload.get("total") or (200000 if cycle == "Lycée" else 150000))
        motif = (payload.get("motif") or "").strip() or "Frais de scolarité"
        paiement = Paiement(
            school_id=eleve.school_id, eleve_id=eleve_id, motif=motif, total=total
        )
        db.add(paiement)
        db.flush()

    versement = Versement(
        school_id=eleve.school_id,
        paiement_id=paiement.id,
        montant=montant,
        date=date.fromisoformat(payload.get("date", date.today().isoformat())),
        mode=payload.get("mode", "Espèces"),
    )
    db.add(versement)
    db.commit()
    db.refresh(paiement)
    return _paiement_out(db, paiement)
