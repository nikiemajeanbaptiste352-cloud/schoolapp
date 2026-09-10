"""Tests — routes d'écriture branchées sur l'interface (UI → API).

Couverture : CRUD enseignants, suppression d'une note, encaissement d'un
versement avec création automatique du dossier. Les élèves créés sont
supprimés en fin de test (try/finally) pour ne pas perturber les autres
tests (effectifs, moyennes du seed).
"""

from __future__ import annotations


def _premiere_classe(client, admin_token: str) -> dict:
    classes = client.get(
        "/api/v1/classes", headers={"Authorization": f"Bearer {admin_token}"}
    ).json()["classes"]
    assert classes, "Aucune classe dans le seed de test"
    return classes[0]


def _creer_eleve_jetable(client, admin_token: str, classe: dict) -> str:
    resp = client.post(
        "/api/v1/eleves/",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "nom": "Jetable",
            "prenom": "Test",
            "sexe": "M",
            "naissance": "2012-01-01",
            "classe": classe["id"],
            "statut": "Actif",
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# Enseignants — CRUD (admin)
# ---------------------------------------------------------------------------
def test_creer_modifier_supprimer_enseignant(client, admin_token):
    from tests.conftest import h

    classes = client.get("/api/v1/classes", headers=h(admin_token)).json()["classes"]
    ids = [c["id"] for c in classes[:2]]

    # Création
    resp = client.post(
        "/api/v1/enseignants",
        headers=h(admin_token),
        json={
            "nom": "Zongo",
            "prenom": "Awa",
            "sexe": "F",
            "tel": "0700000000",
            "email": "awa.zongo@exemple.edu",
            "matiere": "S1",
            "classes": ids,
            "statut": "Actif",
        },
    )
    assert resp.status_code == 200, resp.text
    ens = resp.json()
    assert ens["id"].startswith("T")
    assert ens["nom"] == "Zongo"
    assert ens["prenom"] == "Awa"
    assert ens["matiere"] == "S1"
    assert set(ens["classes"]) == set(ids)

    try:
        # Modification (matière + classes + statut)
        maj = client.put(
            f"/api/v1/enseignants/{ens['id']}",
            headers=h(admin_token),
            json={
                "nom": "Zongo",
                "prenom": "Awa",
                "sexe": "F",
                "tel": ens["tel"],
                "email": ens["email"],
                "matiere": "S2",
                "classes": [ids[0]],
                "statut": "Inactif",
            },
        )
        assert maj.status_code == 200, maj.text
        modifie = maj.json()
        assert modifie["matiere"] == "S2"
        assert modifie["classes"] == [ids[0]]
        assert modifie["statut"] == "Inactif"

        # Validation : matière inconnue → 400
        invalide = client.put(
            f"/api/v1/enseignants/{ens['id']}",
            headers=h(admin_token),
            json={"nom": "Zongo", "prenom": "Awa", "matiere": "S99"},
        )
        assert invalide.status_code == 400

        # Suppression
        sup = client.delete(f"/api/v1/enseignants/{ens['id']}", headers=h(admin_token))
        assert sup.status_code == 200, sup.text
        assert client.get(
            f"/api/v1/enseignants/{ens['id']}", headers=h(admin_token)
        ).status_code == 404
        liste = client.get("/api/v1/enseignants", headers=h(admin_token)).json()["enseignants"]
        assert all(e["id"] != ens["id"] for e in liste)
    finally:
        client.delete(f"/api/v1/enseignants/{ens['id']}", headers=h(admin_token))


def test_ecriture_enseignant_reservee_admin(client, admin_token):
    from tests.conftest import auth, h

    t = auth(client, "j.ouedraogo@lesavoir.edu")  # professeur
    resp = client.post(
        "/api/v1/enseignants",
        headers=h(t),
        json={"nom": "X", "prenom": "Y", "matiere": "S1", "classes": []},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Notes — suppression d'une note précise
# ---------------------------------------------------------------------------
def test_supprimer_une_note(client, admin_token):
    from tests.conftest import h

    classe = _premiere_classe(client, admin_token)
    eid = _creer_eleve_jetable(client, admin_token, classe)
    try:
        detail = client.get(
            f"/api/v1/classes/{classe['id']}", headers=h(admin_token)
        ).json()
        matiere = detail["matieres"][0]
        mid = matiere["id"]

        # La note n'existe pas encore → suppression impossible (404)
        avant = client.delete(
            "/api/v1/notes",
            headers=h(admin_token),
            params={"eleveId": eid, "matiereId": mid, "eval": "Devoir 1"},
        )
        assert avant.status_code == 404

        # Création puis suppression
        put = client.put(
            "/api/v1/notes",
            headers=h(admin_token),
            json={"notes": [{"eleveId": eid, "matiereId": mid, "eval": "Devoir 1", "note": 12}]},
        )
        assert put.status_code == 200, put.text

        sup = client.delete(
            "/api/v1/notes",
            headers=h(admin_token),
            params={"eleveId": eid, "matiereId": mid, "eval": "Devoir 1"},
        )
        assert sup.status_code == 200, sup.text

        notes = client.get(f"/api/v1/notes?classe={classe['id']}", headers=h(admin_token)).json()["notes"]
        assert not any(
            n["eleveId"] == eid and n["matiereId"] == mid and n["eval"] == "Devoir 1"
            for n in notes
        )
    finally:
        client.delete(f"/api/v1/eleves/{eid}", headers=h(admin_token))


def test_prof_peut_supprimer_sa_matiere_pas_une_autre(client, admin_token):
    from tests.conftest import auth, h

    classe = _premiere_classe(client, admin_token)
    eid = _creer_eleve_jetable(client, admin_token, classe)
    t = auth(client, "j.ouedraogo@lesavoir.edu")  # enseigne S1
    try:
        # S2 hors de sa matière → 403 (avant même l'existence de la note)
        refus = client.delete(
            "/api/v1/notes",
            headers=h(t),
            params={"eleveId": eid, "matiereId": "S2", "eval": "Devoir 1"},
        )
        assert refus.status_code == 403
    finally:
        client.delete(f"/api/v1/eleves/{eid}", headers=h(admin_token))


# ---------------------------------------------------------------------------
# Paiements — versement avec création automatique du dossier
# ---------------------------------------------------------------------------
def test_versement_cree_dossier_par_defaut(client, admin_token):
    from tests.conftest import h

    classe = _premiere_classe(client, admin_token)
    attendu = 200000 if classe["cycle"] == "Lycée" else 150000
    eid = _creer_eleve_jetable(client, admin_token, classe)
    try:
        # Aucun dossier avant l'encaissement
        fiche = client.get(f"/api/v1/eleves/{eid}", headers=h(admin_token)).json()
        assert fiche["paiement"] is None

        resp = client.post(
            f"/api/v1/paiements/{eid}/versements",
            headers=h(admin_token),
            json={"montant": 5000, "mode": "Espèces", "date": "2026-09-08"},
        )
        assert resp.status_code == 200, resp.text
        paiement = resp.json()
        assert paiement["eleveId"] == eid
        assert paiement["total"] == attendu
        assert paiement["paye"] == 5000
        assert paiement["restant"] == attendu - 5000
        assert paiement["statut"] == "Partiellement payé"
        assert paiement["versements"][-1]["montant"] == 5000

        # Le dossier est bien persistant (fiche élève)
        fiche2 = client.get(f"/api/v1/eleves/{eid}", headers=h(admin_token)).json()
        assert fiche2["paiement"] is not None
        assert fiche2["paiement"]["total"] == attendu
    finally:
        client.delete(f"/api/v1/eleves/{eid}", headers=h(admin_token))


def test_versement_reserve_admin(client, admin_token):
    from tests.conftest import auth, h

    # EL001 possède déjà un dossier dans le seed
    t = auth(client, "j.ouedraogo@lesavoir.edu")
    resp = client.post(
        "/api/v1/paiements/EL001/versements",
        headers=h(t),
        json={"montant": 1000, "mode": "Espèces", "date": "2026-09-08"},
    )
    assert resp.status_code == 403
