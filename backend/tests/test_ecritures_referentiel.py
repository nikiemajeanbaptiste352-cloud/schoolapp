"""Tests — référentiel éditable (classes / matières / école).

Les classes et matières étaient en lecture seule ; elles sont désormais
gérables par l'administrateur pour bootstraper une base vide depuis
l'interface. Couverture : CRUD classes, CRUD matières (avec détachement des
enseignants), fiche école (mise à jour + refus de doublon), gardes de
sécurité (classes non vides, matières utilisées, rôles).
"""

from __future__ import annotations


def _h(client, admin_token):
    from tests.conftest import h

    return h(admin_token)


def _classe_seeded(client, h, code: str) -> dict:
    classes = client.get("/api/v1/classes", headers=h).json()["classes"]
    for c in classes:
        if c["id"] == code:
            return c
    raise AssertionError(f"Classe seed {code} absente")


# ---------------------------------------------------------------------------
# Classes — CRUD (admin)
# ---------------------------------------------------------------------------
def test_creer_modifier_supprimer_classe(client, admin_token):
    h = _h(client, admin_token)

    # Création d'une classe hors programme (ex. 6C)
    crea = client.post(
        "/api/v1/classes",
        headers=h,
        json={"id": "6C", "nom": "6e C", "cycle": "Collège", "salle": "C-103", "principal": None},
    )
    assert crea.status_code == 200, crea.text
    cls = crea.json()
    assert cls["id"] == "6C"
    assert cls["nom"] == "6e C"
    assert cls["cycle"] == "Collège"
    assert cls["principal"] is None
    assert cls["effectif"] == 0

    try:
        # Visible dans la liste (les codes hors programme s'ajoutent en fin)
        liste = client.get("/api/v1/classes", headers=h).json()["classes"]
        assert any(c["id"] == "6C" for c in liste)

        # Modification (cycle/salle/principal partiels suffisent)
        maj = client.put(
            "/api/v1/classes/6C",
            headers=h,
            json={"cycle": "Lycée", "salle": "L-201"},
        )
        assert maj.status_code == 200, maj.text
        modifie = maj.json()
        assert modifie["cycle"] == "Lycée"
        assert modifie["salle"] == "L-201"

        # Validation : cycle inconnu → 400
        bad = client.put("/api/v1/classes/6C", headers=h, json={"cycle": "Primaire"})
        assert bad.status_code == 400

        # Validation : principal inconnu → 400
        bad2 = client.put("/api/v1/classes/6C", headers=h, json={"principal": "T999"})
        assert bad2.status_code == 400

        # Suppression (classe vide) → OK
        sup = client.delete("/api/v1/classes/6C", headers=h)
        assert sup.status_code == 200, sup.text
        assert client.get("/api/v1/classes/6C", headers=h).status_code == 404
    finally:
        client.delete("/api/v1/classes/6C", headers=h)


def test_classe_dupliquee_refusee(client, admin_token):
    h = _h(client, admin_token)
    resp = client.post(
        "/api/v1/classes",
        headers=h,
        json={"id": "6A", "nom": "6e A", "cycle": "Collège"},
    )
    assert resp.status_code == 409


def test_suppression_classe_non_vide_refusee(client, admin_token):
    h = _h(client, admin_token)
    seeded = _classe_seeded(client, h, "6A")
    assert seeded["effectif"] > 0, "La classe 6A du seed devrait avoir des élèves"
    resp = client.delete("/api/v1/classes/6A", headers=h)
    assert resp.status_code == 409
    # La classe existe toujours
    assert client.get("/api/v1/classes/6A", headers=h).status_code == 200


def test_ecriture_classe_reservee_admin(client, admin_token):
    from tests.conftest import auth

    t = auth(client, "j.ouedraogo@lesavoir.edu")  # professeur
    resp = client.post(
        "/api/v1/classes",
        headers={"Authorization": f"Bearer {t}"},
        json={"id": "6D", "nom": "6e D", "cycle": "Collège"},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Matières — CRUD (admin)
# ---------------------------------------------------------------------------
def test_creer_modifier_supprimer_matiere(client, admin_token):
    h = _h(client, admin_token)

    crea = client.post(
        "/api/v1/matieres",
        headers=h,
        json={"nom": "Informatique", "coef": 2, "icone": "💻", "couleur": "blue"},
    )
    assert crea.status_code == 200, crea.text
    mat = crea.json()
    assert mat["id"].startswith("S")
    assert mat["nom"] == "Informatique"
    assert mat["coef"] == 2

    try:
        # Visible dans la liste
        liste = client.get("/api/v1/matieres", headers=h).json()["matieres"]
        assert any(m["id"] == mat["id"] for m in liste)

        # Modification
        maj = client.put(
            f"/api/v1/matieres/{mat['id']}",
            headers=h,
            json={"nom": "Informatique & Coding", "coef": 3},
        )
        assert maj.status_code == 200, maj.text
        modifie = maj.json()
        assert modifie["nom"] == "Informatique & Coding"
        assert modifie["coef"] == 3

        # Validation : coef invalide → 400
        bad = client.put(f"/api/v1/matieres/{mat['id']}", headers=h, json={"coef": 0})
        assert bad.status_code == 400

        # Suppression (aucune note ni enseignant rattaché) → OK
        sup = client.delete(f"/api/v1/matieres/{mat['id']}", headers=h)
        assert sup.status_code == 200, sup.text
        liste2 = client.get("/api/v1/matieres", headers=h).json()["matieres"]
        assert all(m["id"] != mat["id"] for m in liste2)
    finally:
        client.delete(f"/api/v1/matieres/{mat['id']}", headers=h)


def test_suppression_matiere_detache_enseignants(client, admin_token):
    h = _h(client, admin_token)

    # Matière jetable + enseignant jetable rattaché
    crea = client.post(
        "/api/v1/matieres",
        headers=h,
        json={"nom": "Robotique", "coef": 1, "icone": "🤖", "couleur": "red"},
    )
    assert crea.status_code == 200, crea.text
    mid = crea.json()["id"]

    ens = None
    try:
        resp = client.post(
            "/api/v1/enseignants",
            headers=h,
            json={"nom": "Kaboré", "prenom": "Idriss", "sexe": "M", "matiere": mid, "classes": []},
        )
        assert resp.status_code == 200, resp.text
        ens = resp.json()

        # Suppression de la matière → l'enseignant est détaché
        sup = client.delete(f"/api/v1/matieres/{mid}", headers=h)
        assert sup.status_code == 200, sup.text
        detail = client.get(f"/api/v1/enseignants/{ens['id']}", headers=h).json()
        assert detail["matiere"] is None
    finally:
        if ens:
            client.delete(f"/api/v1/enseignants/{ens['id']}", headers=h)
        client.delete(f"/api/v1/matieres/{mid}", headers=h)


def test_suppression_matiere_avec_notes_refusee(client, admin_token):
    h = _h(client, admin_token)
    # S1 est utilisée par les notes du seed (prof T001 rattaché également)
    resp = client.delete("/api/v1/matieres/S1", headers=h)
    assert resp.status_code == 409
    assert client.get("/api/v1/matieres", headers=h).status_code == 200


def test_ecriture_matiere_reservee_admin(client, admin_token):
    from tests.conftest import auth

    t = auth(client, "j.ouedraogo@lesavoir.edu")  # professeur
    resp = client.post(
        "/api/v1/matieres",
        headers={"Authorization": f"Bearer {t}"},
        json={"nom": "Interdite", "coef": 1},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# École — fiche (admin)
# ---------------------------------------------------------------------------
def test_modifier_ecole(client, admin_token):
    h = _h(client, admin_token)
    avant = client.get("/api/v1/ecole", headers=h)
    assert avant.status_code == 200, avant.text

    maj = client.put("/api/v1/ecole", headers=h, json={"slogan": "Travail, discipline, réussite"})
    assert maj.status_code == 200, maj.text
    assert maj.json()["slogan"] == "Travail, discipline, réussite"

    # L'école existe déjà → POST de création refusé (409)
    doublon = client.post("/api/v1/ecole", headers=h, json={"nom": "Autre école"})
    assert doublon.status_code == 409


def test_modifier_ecole_reservee_admin(client, admin_token):
    from tests.conftest import auth

    t = auth(client, "j.ouedraogo@lesavoir.edu")  # professeur
    resp = client.put("/api/v1/ecole", headers={"Authorization": f"Bearer {t}"}, json={"nom": "Hack"})
    assert resp.status_code == 403
