"""Tests multi-établissements (Phase 2 — isolation school_id).

Deux écoles cohabitent sur la même base SQLite de test :
- école n°1 « CSP Le Savoir » (seed de démonstration, `admin@lesavoir.edu`) ;
- école n°2 « Collège Notre-Dame de Kaya », créée par ce module avec des codes
  métier **volontairement identiques** (3A, S1, EL001, A1…) pour prouver que
  l'isolation est portée par la clé composite `(school_id, id)` et non par la
  rareté des codes.

Le compte direction de l'école n°2 (`dir@cnd-kaya.edu`, même mot de passe de
démo) est rattaché à `school_id=2` : chaque requête authentifiée est donc
exécutée dans le contexte de son école.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from app.database import SessionLocal
from app.models import (
    Annonce,
    Classe,
    Ecole,
    Eleve,
    Matiere,
    Note,
    Paiement,
    Parent,
    User,
    classe_matiere,
)
from app.security import hash_password
from tests.conftest import auth

EMAIL_DIR2 = "dir@cnd-kaya.edu"
PWD_DEMO = "Savoir2026!"

# Données de l'école n°2 (miroir partiel volontaire des codes de l'école n°1).
_ECOLE2 = {
    "nom": "Collège Notre-Dame de Kaya",
    "sigle": "CND Kaya",
    "slogan": "Savoir et vertu",
    "annee": "2026 – 2027",
    "devise": "FCFA",
    "telephone": "+226 00 00 00 00",
    "email": "contact@cnd-kaya.edu",
    "adresse": "Kaya — Burkina Faso",
    "version": "1.0.0",
}


def _creer_ecole2() -> int:
    """Insère l'école n°2 (idempotent) puis renvoie son id (2)."""
    with SessionLocal() as db:
        if db.get(Ecole, 2) is not None:
            return 2
        db.add(Ecole(id=2, **_ECOLE2))
        # Mêmes codes métier que l'école n°1 : 3A / S1 / EL001 / A1.
        db.add(
            Classe(
                school_id=2, id="3A", nom="3e A Bilingue",
                cycle="Collège", salle="K-01", principal_id=None,
            )
        )
        db.add(
            Matiere(
                school_id=2, id="S1", nom="Algèbre",
                coef=4, icone="📐", couleur="blue",
            )
        )
        db.execute(
            classe_matiere.insert().values(
                school_id=2, classe_id="3A", matiere_id="S1", ordre=0,
            )
        )
        parent = Parent(
            school_id=2,
            nom="Kaboré Issa",
            lien="Père",
            tel="70 00 00 00 00",
            email="issa.kabore@mail.com",
            profession="Commerçant",
            adresse="Kaya",
        )
        db.add(parent)
        db.flush()
        db.add(
            Eleve(
                school_id=2, id="EL001", nom="Kaboré", prenom="Zara",
                sexe="F", naissance=date(2012, 3, 5),
                classe_id="3A", statut="Actif",
                inscription=date(2026, 9, 15), parent_id=parent.id,
            )
        )
        db.add(
            Paiement(
                school_id=2, eleve_id="EL001",
                motif="Frais de scolarité 2026 – 2027", total=150000,
            )
        )
        db.add(
            Annonce(
                school_id=2, id="A1", titre="Bienvenue à Notre-Dame",
                contenu="La rentrée est fixée au 5 octobre.",
                categorie="Information", date=date(2026, 9, 20),
                auteur="Direction", important=False,
            )
        )
        db.add(
            User(
                email=EMAIL_DIR2,
                password_hash=hash_password(PWD_DEMO),
                role="Administrateur",
                nom="Directeur CND",
                actif=True,
                school_id=2,
            )
        )
        db.commit()
    return 2


@pytest.fixture(scope="session")
def ecole2(client) -> int:
    """École n°2 prête (après le seed de l'école n°1 par le lifespan)."""
    return _creer_ecole2()


@pytest.fixture(scope="session")
def token_dir2(client, ecole2) -> str:
    return auth(client, EMAIL_DIR2)


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _notes_scolaires(eleve_id: str, matiere_id: str, eval_nom: str) -> dict[int, float]:
    """Valeur de note par école pour un triplet identique (contrôle direct DB)."""
    with SessionLocal() as db:
        rows = db.execute(
            select(Note).where(
                Note.eleve_id == eleve_id,
                Note.matiere_id == matiere_id,
                Note.eval == eval_nom,
            )
        ).scalars().all()
        return {r.school_id: r.note for r in rows}


# ---------------------------------------------------------------------------
# 1. Deux écoles, mêmes codes métier, données distinctes
# ---------------------------------------------------------------------------
def test_deux_ecoles_partagent_les_codes_mais_pas_les_donnees(
    client, admin_token, token_dir2
):
    h1, h2 = _h(admin_token), _h(token_dir2)

    # La fiche « école » lue dépend du compte connecté.
    e1 = client.get("/api/v1/ecole", headers=h1).json()
    e2 = client.get("/api/v1/ecole", headers=h2).json()
    assert e1["nom"] == "Complexe Scolaire Privé Le Savoir"
    assert e2["nom"] == _ECOLE2["nom"]
    assert e1["nom"] != e2["nom"]

    # Même code de classe « 3A » présent dans les deux écoles, mais contenu propre.
    c1 = client.get("/api/v1/classes/3A", headers=h1).json()
    c2 = client.get("/api/v1/classes/3A", headers=h2).json()
    assert c1["id"] == c2["id"] == "3A"
    assert c1["nom"] != c2["nom"]
    assert c2["nom"] == "3e A Bilingue"

    # Même matricule « EL001 » : chaque école voit SON élève.
    l1 = client.get("/api/v1/eleves/EL001", headers=h1)
    l2 = client.get("/api/v1/eleves/EL001", headers=h2)
    assert l1.status_code == l2.status_code == 200
    assert l2.json()["nom"] == "Kaboré"


# ---------------------------------------------------------------------------
# 2. Les listes sont scopées : chaque école ne voit que ses lignes
# ---------------------------------------------------------------------------
def test_listes_scopes_par_ecole(client, admin_token, token_dir2, ecole2):
    h1, h2 = _h(admin_token), _h(token_dir2)

    eleves1 = client.get("/api/v1/eleves/", headers=h1).json()["eleves"]
    eleves2 = client.get("/api/v1/eleves/", headers=h2).json()["eleves"]
    assert len(eleves2) == 1
    assert eleves2[0]["id"] == "EL001" and eleves2[0]["prenom"] == "Zara"
    assert all(e["prenom"] != "Zara" for e in eleves1)

    classes2 = client.get("/api/v1/classes", headers=h2).json()["classes"]
    assert len(classes2) == 1 and classes2[0]["id"] == "3A"

    matieres1 = client.get("/api/v1/matieres", headers=h1).json()["matieres"]
    matieres2 = client.get("/api/v1/matieres", headers=h2).json()["matieres"]
    assert len(matieres2) == 1 and matieres2[0]["nom"] == "Algèbre"
    assert all(m["nom"] != "Algèbre" for m in matieres1)


# ---------------------------------------------------------------------------
# 3. Accès croisé interdit : l'école n°2 ne voit pas les lignes de l'école n°1
# ---------------------------------------------------------------------------
def test_acces_croise_introuvable(client, admin_token, token_dir2, ecole2):
    h1, h2 = _h(admin_token), _h(token_dir2)

    # EL002 et la classe 6A n'existent que dans l'école n°1.
    assert client.get("/api/v1/eleves/EL002", headers=h1).status_code == 200
    assert client.get("/api/v1/eleves/EL002", headers=h2).status_code == 404
    assert client.get("/api/v1/classes/6A", headers=h1).status_code == 200
    assert client.get("/api/v1/classes/6A", headers=h2).status_code == 404


# ---------------------------------------------------------------------------
# 4. Notes : upsert par école, aucun écrasement entre écoles
# ---------------------------------------------------------------------------
def test_notes_scopes_par_ecole_sans_ecrasement(client, token_dir2, ecole2):
    h2 = _h(token_dir2)
    avant = _notes_scolaires("EL001", "S1", "Devoir 1")

    resp = client.put(
        "/api/v1/notes",
        headers=h2,
        json={"notes": [{"eleveId": "EL001", "matiereId": "S1",
                         "eval": "Devoir 1", "note": 17}]},
    )
    assert resp.status_code == 200, resp.text

    apres = _notes_scolaires("EL001", "S1", "Devoir 1")
    assert apres.get(2) == 17.0  # note créée dans l'école n°2
    if 1 in avant:
        assert apres.get(1) == avant[1]  # note de l'école n°1 inchangée
    assert 2 not in avant  # aucun triplet n'existait pour l'école n°2 avant


# ---------------------------------------------------------------------------
# 5. Encaissement : le versement est rattaché à la bonne école
# ---------------------------------------------------------------------------
def test_encaissement_versement_dans_la_bonne_ecole(client, admin_token, token_dir2, ecole2):
    h1, h2 = _h(admin_token), _h(token_dir2)

    # Le dossier EL001 de l'école n°1 (seed) n'a pas encore de versement de 30 000.
    f1_avant = client.get("/api/v1/eleves/EL001", headers=h1).json()
    montants1_avant = [v["montant"] for v in (f1_avant.get("paiement") or {}).get("versements", [])]
    assert 30000 not in montants1_avant

    resp = client.post(
        "/api/v1/paiements/EL001/versements",
        headers=h2,
        json={"montant": 30000, "mode": "Espèces", "date": "2026-10-05"},
    )
    assert resp.status_code == 200, resp.text
    versements2 = resp.json().get("versements", [])
    assert any(v["montant"] == 30000 for v in versements2)

    # L'école n°1 n'a pas reçu ce versement (son EL001 reste inchangé).
    f1_apres = client.get("/api/v1/eleves/EL001", headers=h1).json()
    montants1_apres = [v["montant"] for v in (f1_apres.get("paiement") or {}).get("versements", [])]
    assert montants1_apres == montants1_avant


# ---------------------------------------------------------------------------
# 6. Annonces : création et lecture isolées
# ---------------------------------------------------------------------------
def test_annonces_isolees_par_ecole(client, admin_token, token_dir2, ecole2):
    h1, h2 = _h(admin_token), _h(token_dir2)

    # Chaque école voit ses propres annonces (même id A1, contenu différent).
    ann1 = client.get("/api/v1/annonces", headers=h1).json()["annonces"]
    ann2 = client.get("/api/v1/annonces", headers=h2).json()["annonces"]
    assert ann1 and ann2
    assert ann2[0]["id"] == "A1"
    assert all(a["titre"] != "Bienvenue à Notre-Dame" for a in ann1)

    # Une annonce créée par l'école n°2 n'apparaît que dans l'école n°2.
    crea = client.post(
        "/api/v1/annonces",
        headers=h2,
        json={
            "titre": "Vente de tenues ND",
            "contenu": "Inscriptions auprès de la vie scolaire.",
            "categorie": "Information",
            "date": "2026-09-25",
        },
    )
    assert crea.status_code == 200, crea.text
    assert crea.json()["titre"] == "Vente de tenues ND"

    titres1 = [a["titre"] for a in client.get("/api/v1/annonces", headers=h1).json()["annonces"]]
    titres2 = [a["titre"] for a in client.get("/api/v1/annonces", headers=h2).json()["annonces"]]
    assert "Vente de tenues ND" not in titres1
    assert "Vente de tenues ND" in titres2
