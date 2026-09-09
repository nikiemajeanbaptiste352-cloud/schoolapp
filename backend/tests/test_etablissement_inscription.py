"""Tests de la porte d'entrée « Établissement » : création du compte Administrateur."""

from __future__ import annotations


def test_inscription_etablissement_cree_administrateur(client):
    """L'inscription d'un établissement crée un compte Administrateur actif et connecte."""
    email = "direction.sap@exemple.com"
    resp = client.post(
        "/api/v1/auth/inscription-etablissement",
        json={
            "ecole": "Complexe Scolaire Exemple",
            "nom": "Directrice Exemple",
            "email": email,
            "password": "Secret123!",
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["access_token"]
    assert data["user"]["email"] == email
    assert data["user"]["role"] == "Administrateur"
    assert data["user"]["actif"] is True

    # Le compte créé peut ensuite se connecter avec le mot de passe choisi.
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Secret123!"},
    )
    assert login.status_code == 200, login.text
    assert login.json()["user"]["role"] == "Administrateur"


def test_inscription_etablissement_sans_nom_ecole_accepte(client):
    """Le nom d'établissement est optionnel quand l'école est déjà configurée."""
    email = "adjoint.exemple@exemple.com"
    resp = client.post(
        "/api/v1/auth/inscription-etablissement",
        json={"nom": "Adjoint Exemple", "email": email, "password": "Secret123!"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["user"]["role"] == "Administrateur"


def test_inscription_etablissement_refuse_email_deja_utilise(client):
    """Un email déjà présent (admin de démo) n'est pas réinscriptible : 409."""
    resp = client.post(
        "/api/v1/auth/inscription-etablissement",
        json={
            "ecole": "Mon école",
            "nom": "Doublon",
            "email": "admin@lesavoir.edu",
            "password": "Secret123!",
        },
    )
    assert resp.status_code == 409


def test_inscription_etablissement_exige_mot_de_passe_minimum(client):
    resp = client.post(
        "/api/v1/auth/inscription-etablissement",
        json={
            "ecole": "Mon école",
            "nom": "Faible",
            "email": "etab.faible@exemple.com",
            "password": "123",
        },
    )
    assert resp.status_code == 422


def test_inscription_etablissement_refuse_nom_vide(client):
    resp = client.post(
        "/api/v1/auth/inscription-etablissement",
        json={
            "ecole": "Mon école",
            "nom": "   ",
            "email": "etab.nomvide@exemple.com",
            "password": "Secret123!",
        },
    )
    assert resp.status_code == 422


def test_inscription_parent_refuse_toujours_role_admin(client):
    """La porte Parent ne crée jamais de compte Administrateur."""
    email = "parent.eco@exemple.com"
    resp = client.post(
        "/api/v1/auth/inscription",
        json={"nom": "Parent École", "email": email, "password": "Secret123!"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["user"]["role"] == "Parent"
