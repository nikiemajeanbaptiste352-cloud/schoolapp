"""Phase 1 — cloisonnement des lectures par rôle effectif.

Ce module vérifie le livrable de la Phase 1 : **aucune route de lecture ne
renvoie les données d'un tiers**. La matrice testée est celle de
`app/services/perimetre.py` :

==============  =================  ================  ==========  ==========
Rôle            élèves             notes             présences   finances
==============  =================  ================  ==========  ==========
Administrateur  tous               toutes            toutes      toutes
Professeur      tous               sa matière        toutes      aucune
Surveillant     tous               aucune            toutes      aucune
Élève           lui seul           les siennes       les siennes les siennes
Parent          ses enfants       de ses enfants    idem        idem
==============  =================  ================  ==========  ==========

Le test « compte Parent neuf » est le cœur de la non-régression : avant la
Phase 1, `GET /api/v1/etat` servait l'établissement entier à n'importe quel
compte authentifié.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.database import SessionLocal
from app.models import Membership, User
from app.security import hash_password
from app.services.membres import definir_membre
from tests.conftest import auth, h

EMAIL_ELEVE = "paul.kabore@lesavoir.edu"  # EL001, classe 3A
EMAIL_PROF = "j.ouedraogo@lesavoir.edu"  # T001, matière S1
EMAIL_SURV = "surveillant.phase1@lesavoir.edu"
PWD_DEMO = "Savoir2026!"


def _etat(client, token: str) -> dict:
    resp = client.get("/api/v1/etat", headers=h(token))
    assert resp.status_code == 200, resp.text
    return resp.json()


def _ids_eleves(etat: dict) -> set[str]:
    return {e["id"] for e in etat["eleves"]}


# ---------------------------------------------------------------------------
# Comptes de test
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def eleve_token(client) -> str:
    return auth(client, EMAIL_ELEVE)


@pytest.fixture(scope="module")
def parent_token(client) -> str:
    """Parent d'EL001 : l'email est lu sur la fiche de l'élève (données seed)."""
    admin = auth(client, "admin@lesavoir.edu")
    fiche = client.get("/api/v1/eleves/EL001", headers=h(admin)).json()
    return auth(client, fiche["parent"]["email"])


@pytest.fixture(scope="module")
def prof_token(client) -> str:
    return auth(client, EMAIL_PROF)


@pytest.fixture(scope="module")
def surveillant_token(client):
    """Crée un Surveillant rattaché à l'établissement n°1, puis le supprime.

    Le seed ne fournit pas de compte Surveillant ; il est donc fabriqué ici,
    et retiré au démontage pour laisser la base dans son état initial.
    """
    from app.auth import ROLE_SURVEILLANT

    with SessionLocal() as db:
        admin = db.scalar(select(User).where(User.email == "admin@lesavoir.edu"))
        assert admin is not None and admin.school_id is not None, "seed absent"
        sid = admin.school_id

        user = db.scalar(select(User).where(User.email == EMAIL_SURV))
        if user is None:
            user = User(
                email=EMAIL_SURV,
                password_hash=hash_password(PWD_DEMO),
                role=ROLE_SURVEILLANT,
                nom="Surveillant Phase 1",
                actif=True,
                school_id=sid,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        definir_membre(db, user, sid, ROLE_SURVEILLANT, "actif")
        db.commit()
        uid = user.id

    yield auth(client, EMAIL_SURV)

    with SessionLocal() as db:
        for membre in db.execute(
            select(Membership).where(Membership.user_id == uid)
        ).scalars():
            db.delete(membre)
        restant = db.get(User, uid)
        if restant is not None:
            db.delete(restant)
        db.commit()


# ---------------------------------------------------------------------------
# 1. Administrateur : référence non régressée
# ---------------------------------------------------------------------------
def test_administrateur_voit_tout_l_etablissement(client, admin_token):
    etat = _etat(client, admin_token)
    assert len(etat["eleves"]) == 15
    assert len(etat["classes"]) == 10
    assert len(etat["matieres"]) == 8
    assert len(etat["enseignants"]) == 7
    assert len(etat["paiements"]) == 15
    assert len(etat["presences"]) == 15 * 12
    # Coordonnées servies à l'encadrement
    assert any(e["tel"] for e in etat["enseignants"])
    # Pas de rang injecté en vue complète (le front le calcule lui-même)
    assert all("rang" not in e for e in etat["eleves"])


# ---------------------------------------------------------------------------
# 2. Élève : sa fiche, ses notes, ses présences, son paiement
# ---------------------------------------------------------------------------
def test_etat_eleve_reduit_a_sa_seule_fiche(client, eleve_token):
    etat = _etat(client, eleve_token)
    assert _ids_eleves(etat) == {"EL001"}

    # Rang fourni par le serveur : le navigateur n'a plus la classe entière.
    fiche = etat["eleves"][0]
    assert "rang" in fiche and fiche["rang"]["total"] > 1

    assert etat["notes"], "un élève doit voir ses propres notes"
    assert {n["eleveId"] for n in etat["notes"]} == {"EL001"}
    assert {p["eleveId"] for p in etat["presences"]} == {"EL001"}
    assert {p["eleveId"] for p in etat["paiements"]} == {"EL001"}

    # Ni l'annuaire des enseignants, ni la finance des autres.
    assert all(e["tel"] == "" and e["email"] == "" for e in etat["enseignants"])


def test_eleve_ne_voit_pas_les_paiements_des_autres(client, eleve_token):
    resp = client.get("/api/v1/paiements", headers=h(eleve_token))
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert {p["eleveId"] for p in data["paiements"]} == {"EL001"}
    assert data["total"] == len(data["paiements"]) >= 1

    stats = client.get("/api/v1/paiements/stats", headers=h(eleve_token))
    assert stats.status_code == 200, stats.text


# ---------------------------------------------------------------------------
# 3. Parent : ses enfants uniquement
# ---------------------------------------------------------------------------
def test_compte_parent_neuf_ne_voit_qu_un_eleve(client, parent_token):
    etat = _etat(client, parent_token)
    assert _ids_eleves(etat) == {"EL001"}
    assert len(etat["eleves"]) == 1
    assert {p["eleveId"] for p in etat["paiements"]} == {"EL001"}
    assert all(e["tel"] == "" for e in etat["enseignants"])

    # Aucun bulletin d'autrui
    bulletins = client.get("/api/v1/classes/3A/bulletins", headers=h(parent_token))
    assert bulletins.status_code == 200, bulletins.text
    lignes = bulletins.json()["bulletins"]
    assert {b["eleveId"] for b in lignes} == {"EL001"}


# ---------------------------------------------------------------------------
# 4. Professeur : tous les élèves, sa matière, aucune finance
# ---------------------------------------------------------------------------
def test_etat_prof_sa_matiere_sans_finance(client, prof_token):
    etat = _etat(client, prof_token)
    assert len(etat["eleves"]) == 15
    assert all("rang" not in e for e in etat["eleves"])
    assert etat["notes"] and {n["matiereId"] for n in etat["notes"]} == {"S1"}
    assert etat["presences"], "les présences restent visibles pour un professeur"
    assert etat["paiements"] == []

    assert client.get("/api/v1/paiements", headers=h(prof_token)).json()["paiements"] == []
    assert client.get("/api/v1/paiements/stats", headers=h(prof_token)).status_code == 200


# ---------------------------------------------------------------------------
# 5. Surveillant : vie scolaire sans notes ni finance
# ---------------------------------------------------------------------------
def test_etat_surveillant_sans_notes_ni_finance(client, surveillant_token):
    etat = _etat(client, surveillant_token)
    assert len(etat["eleves"]) == 15
    assert etat["presences"], "un surveillant suit les présences"
    assert etat["notes"] == []
    assert etat["paiements"] == []
    assert any(e["tel"] for e in etat["enseignants"])


def test_surveillant_pointe_mais_ne_lit_pas_les_notes(client, surveillant_token):
    t = surveillant_token

    # Pointage autorisé (payload vide → aucun effet sur les données de test)
    resp = client.post(
        "/api/v1/presences",
        headers=h(t),
        json={"classe": "3A", "date": "2026-01-05", "statuts": {}},
    )
    assert resp.status_code == 200, resp.text

    # Notes interdites
    assert client.get("/api/v1/notes/stats?classe=3A", headers=h(t)).status_code == 403
    assert client.get("/api/v1/notes", headers=h(t)).status_code == 403

    # Finance vide
    data = client.get("/api/v1/paiements", headers=h(t)).json()
    assert data["paiements"] == [] and data["total"] == 0

    # Annuaire et fiches élèves accessibles
    assert client.get("/api/v1/eleves/EL001", headers=h(t)).status_code == 200


def test_eleve_ne_peut_pas_pointer(client, eleve_token):
    resp = client.post(
        "/api/v1/presences",
        headers=h(eleve_token),
        json={"classe": "3A", "date": "2026-01-05", "statuts": {}},
    )
    assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# 6. Référentiel : détail de classe et annuaire
# ---------------------------------------------------------------------------
def test_detail_classe_reduit_pour_eleve(client, eleve_token, admin_token):
    sienne = client.get("/api/v1/classes/3A", headers=h(eleve_token))
    assert sienne.status_code == 200, sienne.text
    data = sienne.json()
    assert {e["id"] for e in data["eleves"]} == {"EL001"}
    assert all(e["tel"] == "" and e["email"] == "" for e in data["enseignants"])

    autre = client.get("/api/v1/classes/6A", headers=h(eleve_token))
    assert autre.status_code == 403, autre.text

    # Référence administrateur : classe entière + coordonnées
    ref = client.get("/api/v1/classes/3A", headers=h(admin_token))
    assert ref.status_code == 200, ref.text
    assert len(ref.json()["eleves"]) == 5
    assert any(e["tel"] for e in ref.json()["enseignants"])


def test_emploi_du_temps_cloisonne(client, eleve_token, admin_token):
    assert (
        client.get("/api/v1/classes/3A/emploi-du-temps", headers=h(eleve_token)).status_code
        == 200
    )
    assert (
        client.get("/api/v1/classes/6A/emploi-du-temps", headers=h(eleve_token)).status_code
        == 403
    )
    assert (
        client.get("/api/v1/classes/6A/emploi-du-temps", headers=h(admin_token)).status_code
        == 200
    )


def test_annuaire_masque_pour_eleve_et_parent(client, eleve_token, parent_token, admin_token):
    ref = client.get("/api/v1/enseignants", headers=h(admin_token)).json()["enseignants"]
    t001_ref = next(e for e in ref if e["id"] == "T001")
    assert t001_ref["tel"] and t001_ref["email"]

    for token in (eleve_token, parent_token):
        liste = client.get("/api/v1/enseignants", headers=h(token)).json()["enseignants"]
        assert len(liste) == len(ref)  # les noms restent visibles…
        assert all(e["tel"] == "" and e["email"] == "" for e in liste)  # …pas les coordonnées

        detail = client.get("/api/v1/enseignants/T001", headers=h(token))
        assert detail.status_code == 200, detail.text
        assert detail.json()["tel"] == "" and detail.json()["email"] == ""


# ---------------------------------------------------------------------------
# 7. Bulletins : jamais ceux d'un tiers
# ---------------------------------------------------------------------------
def test_bulletins_reduits_au_perimetre(client, eleve_token, admin_token):
    ref = client.get("/api/v1/classes/3A/bulletins", headers=h(admin_token))
    assert ref.status_code == 200, ref.text
    assert len(ref.json()["bulletins"]) == 5

    perso = client.get("/api/v1/classes/3A/bulletins", headers=h(eleve_token))
    assert perso.status_code == 200, perso.text
    bulletins = perso.json()["bulletins"]
    assert {b["eleveId"] for b in bulletins} == {"EL001"}

    # Classe d'autrui : refus franc (pas de fuite silencieuse)
    assert client.get("/api/v1/classes/6A/bulletins", headers=h(eleve_token)).status_code == 403
