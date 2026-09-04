"""Tests des permissions et des écritures (rôles Administrateur/Professeur)."""

from __future__ import annotations


def test_prof_voit_notes_de_sa_matiere_seulement(client, admin_token):
    from tests.conftest import auth, h

    # T001 = Jean Ouédraogo, enseigne S1 (Mathématiques)
    t = auth(client, "j.ouedraogo@lesavoir.edu")
    resp = client.get("/api/v1/notes", headers=h(t))
    assert resp.status_code == 200
    matieres = {n["matiereId"] for n in resp.json()["notes"]}
    assert matieres == {"S1"}

    # Écriture d'une note S1 autorisée
    ok = client.put(
        "/api/v1/notes",
        headers=h(t),
        json={"notes": [{"eleveId": "EL001", "matiereId": "S1", "eval": "Devoir 1", "note": 15}]},
    )
    assert ok.status_code == 200, ok.text

    # Écriture d'une note hors de sa matière : refusée
    refus = client.put(
        "/api/v1/notes",
        headers=h(t),
        json={"notes": [{"eleveId": "EL001", "matiereId": "S2", "eval": "Devoir 1", "note": 15}]},
    )
    assert refus.status_code == 403


def test_eleve_limite_a_sa_propre_fiche(client):
    from tests.conftest import auth, h

    t = auth(client, "paul.kabore@lesavoir.edu")  # EL001
    assert client.get("/api/v1/eleves/EL001", headers=h(t)).status_code == 200
    assert client.get("/api/v1/eleves/EL002", headers=h(t)).status_code == 403


def test_parent_ne_voit_que_ses_enfants(client):
    from tests.conftest import auth, h

    # Parent d'EL001 (Paul Kaboré) : lié à la fiche parent d'EL001
    parent = client.get("/api/v1/eleves/EL001", headers=h(auth(client, "admin@lesavoir.edu")))
    email_parent = parent.json()["parent"]["email"]
    t = auth(client, email_parent)
    assert client.get("/api/v1/eleves/EL001", headers=h(t)).status_code == 200
    assert client.get("/api/v1/eleves/EL010", headers=h(t)).status_code == 403


def test_ecriture_annonce_reservee_admin(client):
    from tests.conftest import auth, h

    t = auth(client, "j.ouedraogo@lesavoir.edu")
    resp = client.post(
        "/api/v1/annonces",
        headers=h(t),
        json={"titre": "T", "contenu": "C", "date": "2026-12-15"},
    )
    assert resp.status_code == 403
