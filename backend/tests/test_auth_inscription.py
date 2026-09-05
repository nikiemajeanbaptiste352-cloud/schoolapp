"""Tests de l'inscription publique (Parent) et de la gestion des comptes (admin)."""

from __future__ import annotations


def test_inscription_publique_cree_compte_parent(client):
    """Une inscription publique crée un compte Parent actif et connecte."""
    email = "parent.inscrit@exemple.com"
    resp = client.post(
        "/api/v1/auth/inscription",
        json={"nom": "Parent Inscrit", "email": email, "password": "Secret123!"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["access_token"]
    assert data["user"]["email"] == email
    assert data["user"]["role"] == "Parent"
    assert data["user"]["actif"] is True

    # Le compte créé peut ensuite se connecter avec le mot de passe choisi.
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Secret123!"},
    )
    assert login.status_code == 200, login.text


def test_inscription_refuse_email_deja_utilise(client):
    """L'inscription avec un email déjà pris renvoie 409."""
    resp = client.post(
        "/api/v1/auth/inscription",
        json={"nom": "Doublon", "email": "admin@lesavoir.edu", "password": "Secret123!"},
    )
    assert resp.status_code == 409


def test_inscription_exige_mot_de_passe_minimum(client):
    resp = client.post(
        "/api/v1/auth/inscription",
        json={"nom": "Faible", "email": "faible@exemple.com", "password": "123"},
    )
    assert resp.status_code == 422


def test_admin_cree_compte_et_liste(client, admin_token):
    """L'admin crée un compte Professeur puis le retrouve dans la liste."""
    from tests.conftest import h

    email = "prof.cree@exemple.com"
    resp = client.post(
        "/api/v1/auth/comptes",
        headers=h(admin_token),
        json={"nom": "Prof Créé", "email": email, "password": "Motdepasse1!", "role": "Professeur"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["role"] == "Professeur"

    liste = client.get("/api/v1/auth/comptes", headers=h(admin_token))
    assert liste.status_code == 200
    emails = {u["email"] for u in liste.json()}
    assert email in emails


def test_creation_compte_interdite_hors_admin(client):
    """Un utilisateur non-admin ne peut pas créer de compte."""
    from tests.conftest import auth, h

    t = auth(client, "j.ouedraogo@lesavoir.edu")  # Professeur
    resp = client.post(
        "/api/v1/auth/comptes",
        headers=h(t),
        json={"nom": "Intrus", "email": "intrus@exemple.com", "password": "Motdepasse1!", "role": "Parent"},
    )
    assert resp.status_code == 403


def test_liste_comptes_interdite_hors_admin(client):
    from tests.conftest import auth, h

    t = auth(client, "paul.kabore@lesavoir.edu")  # Élève
    resp = client.get("/api/v1/auth/comptes", headers=h(t))
    assert resp.status_code == 403


def test_admin_cree_compte_role_invalide_refuse(client, admin_token):
    from tests.conftest import h

    resp = client.post(
        "/api/v1/auth/comptes",
        headers=h(admin_token),
        json={"nom": "X", "email": "x@exemple.com", "password": "Motdepasse1!", "role": "SuperAdmin"},
    )
    assert resp.status_code == 422
