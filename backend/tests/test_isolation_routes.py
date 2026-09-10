"""Tests — garde-fous d'isolation multi-établissements (Phase 2).

Deux propriétés doivent tenir pour que la Phase 2 ait un sens :

1. **Aucune lecture de domaine sans jeton.** Toutes les routes qui exposent
   des données d'école (classes, matières, enseignants, école, annonces,
   tableau de bord, synthèse des paiements) répondent 401 sans jeton. Sans
   cela, un simple `curl` anonyme lirait l'école n° 1 dès qu'une seconde
   école existe.

2. **Repli mono-école non ambigu.** Le repli de `sd._sid` (aucun contexte
   école) n'est admis que s'il n'existe qu'une seule école en base ; au-delà,
   il échoue explicitement (`EcoleIndeterminee`) au lieu de servir
   silencieusement les données de l'école n° 1.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.database import SessionLocal
from app.models import Ecole
from app.services import sd

# Routes de domaine : données d'établissement, jamais publiques.
ROUTES_PRIVEES = [
    "/api/v1/classes",
    "/api/v1/classes/3A",
    "/api/v1/classes/3A/emploi-du-temps",
    "/api/v1/matieres",
    "/api/v1/enseignants",
    "/api/v1/enseignants/T001",
    "/api/v1/ecole",
    "/api/v1/annonces",
    "/api/v1/dashboard",
    "/api/v1/paiements/stats",
]


@pytest.mark.parametrize("route", ROUTES_PRIVEES)
def test_lecture_domaine_refusee_sans_jeton(client, route):
    """Sans jeton, ces lectures ne doivent plus répondre 200 (401 attendu)."""
    resp = client.get(route)
    assert resp.status_code == 401, f"{route} sans jeton → {resp.status_code}"


@pytest.mark.parametrize("route", ROUTES_PRIVEES)
def test_lecture_domaine_autorisee_avec_jeton(client, admin_token, route):
    """Avec un jeton valide, les mêmes routes restent pleinement fonctionnelles."""
    from tests.conftest import h

    resp = client.get(route, headers=h(admin_token))
    assert resp.status_code == 200, f"{route} avec jeton → {resp.status_code}"


def test_health_anonyme_ne_divulgue_rien(client):
    """La sonde publique informe sur le service, jamais sur l'établissement."""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    corps = resp.json()
    assert corps["status"] == "ok"
    assert corps["counts"] is None
    assert corps["ecole"] is None


def test_contexte_ecole_explicite_prioritaire():
    """Le contexte école posé par l'auth prime sur le repli mono-école."""
    db = SessionLocal()
    try:
        sd.definir_ecole_courante(1)
        assert sd.sid_ecole(db) == 1
    finally:
        sd.definir_ecole_courante(None)
        db.close()


def test_repli_refuse_des_que_deux_ecoles_existent():
    """Avec 2 écoles en base, une consultation sans contexte échoue.

    La seconde école est insérée puis annulée (rollback) : le test est
    autonome et ne laisse aucune trace dans la base de test.
    """
    db = SessionLocal()
    sd.definir_ecole_courante(None)
    try:
        ids_avant = db.scalars(select(Ecole.id).order_by(Ecole.id)).all()
        if len(ids_avant) <= 1:
            # Une seule école → repli mono-école encore toléré.
            assert sd.sid_ecole(db) == (ids_avant[0] if ids_avant else 1)

        db.add(
            Ecole(
                id=9990,
                nom="Établissement de contrôle",
                sigle="CTRL",
                slogan="",
                annee="2026 – 2027",
                devise="FCFA",
                telephone="",
                email="",
                adresse="",
                version="1.0.0",
            )
        )
        db.flush()

        # Deux écoles → plus aucun repli silencieux possible.
        with pytest.raises(sd.EcoleIndeterminee):
            sd.sid_ecole(db)

        # Un contexte explicite reste évidemment accepté.
        assert sd._sid(db, 9990) == 9990
    finally:
        db.rollback()
        sd.definir_ecole_courante(None)
        db.close()
