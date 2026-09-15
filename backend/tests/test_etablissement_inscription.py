"""Tests de la porte d'entrée « Établissement ».

Cette route publique (`POST /auth/inscription-etablissement`) crée un compte
Administrateur. Elle ne doit servir qu'au **bootstrap** d'un déploiement
vierge : dès qu'un établissement existe, elle doit refuser, sinon n'importe
qui sur Internet peut s'octroyer la direction de l'école en production.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture()
def client_vierge(tmp_path):
    """Client branché sur une base **vide** : déploiement pas encore initialisé.

    La session est remplacée par une base SQLite jetable, et le contexte du
    client n'est pas ouvert (donc pas de « lifespan ») pour ne pas ré-amorcer
    la base de démonstration de la session de tests.
    """
    from app.database import Base, get_db
    from app.main import app

    moteur = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'vierge.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(moteur)
    fabrique = sessionmaker(bind=moteur, autoflush=False, expire_on_commit=False)

    def _session():
        db = fabrique()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


def _corps(email: str, ecole: str | None = "Complexe Scolaire Exemple") -> dict:
    corps = {"nom": "Directrice Exemple", "email": email, "password": "Secret123!"}
    if ecole is not None:
        corps["ecole"] = ecole
    return corps


# ---------------------------------------------------------------------------
# Bootstrap : base encore vide
# ---------------------------------------------------------------------------
def test_bootstrap_cree_le_compte_de_direction(client_vierge):
    """Sur une base vierge, l'inscription ouvre l'école et crée un Administrateur actif."""
    email = "direction.sap@exemple.com"
    resp = client_vierge.post(
        "/api/v1/auth/inscription-etablissement", json=_corps(email)
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["access_token"]
    assert data["user"]["email"] == email
    assert data["user"]["role"] == "Administrateur"
    assert data["user"]["actif"] is True

    # Le compte créé se connecte avec le mot de passe choisi et lit la fiche école.
    login = client_vierge.post(
        "/api/v1/auth/login", json={"email": email, "password": "Secret123!"}
    )
    assert login.status_code == 200, login.text
    assert login.json()["user"]["role"] == "Administrateur"

    ecole = client_vierge.get(
        "/api/v1/ecole",
        headers={"Authorization": f"Bearer {data['access_token']}"},
    )
    assert ecole.status_code == 200, ecole.text
    assert ecole.json()["nom"] == "Complexe Scolaire Exemple"


def test_bootstrap_sans_nom_ecole_accepte(client_vierge):
    """Le nom d'établissement est facultatif : un libellé neutre est alors posé."""
    resp = client_vierge.post(
        "/api/v1/auth/inscription-etablissement",
        json={"nom": "Adjoint Exemple", "email": "bootstrap.sansnom@exemple.com",
              "password": "Secret123!"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["user"]["role"] == "Administrateur"
    # La fiche école reste protégée : sans jeton, sa lecture est refusée.
    assert client_vierge.get("/api/v1/ecole").status_code == 401


def test_la_porte_se_referme_des_que_l_ecole_existe(client_vierge):
    """Non-régression : le 2e inscrit n'obtient PAS le rôle Administrateur.

    C'est la faille corrigée — la route attribuait `ROLE_ADMIN` à quiconque
    la remplissait, indéfiniment, sans jeton ni invitation.
    """
    premier = client_vierge.post(
        "/api/v1/auth/inscription-etablissement", json=_corps("direction@exemple.com")
    )
    assert premier.status_code == 201, premier.text

    intrus = client_vierge.post(
        "/api/v1/auth/inscription-etablissement", json=_corps("intrus@exemple.com")
    )
    assert intrus.status_code == 409, intrus.text
    assert "invitation" in intrus.json()["detail"].lower()
    # Aucun jeton n'est délivré : l'intrus n'est pas connecté.
    assert "access_token" not in intrus.json()


# ---------------------------------------------------------------------------
# Établissement déjà configuré : la porte est fermée
# ---------------------------------------------------------------------------
def test_refuse_si_ecole_deja_configuree(client):
    """Sur la base de démonstration (école créée), la route publique refuse."""
    resp = client.post(
        "/api/v1/auth/inscription-etablissement",
        json=_corps("nouvelle.direction@exemple.com"),
    )
    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert "déjà configuré" in detail
    assert "invitation" in detail


def test_refuse_email_deja_utilise(client):
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


def test_exige_mot_de_passe_minimum(client_vierge):
    """Les contrôles de forme sont faits dans le handler : on les teste au bootstrap.

    Sur un établissement déjà configuré, le verrou répond 409 **avant** ces
    contrôles — c'est voulu : la route est fermée, quelle que soit la saisie.
    """
    resp = client_vierge.post(
        "/api/v1/auth/inscription-etablissement",
        json={
            "ecole": "Mon école",
            "nom": "Faible",
            "email": "etab.faible@exemple.com",
            "password": "123",
        },
    )
    assert resp.status_code == 422, resp.text


def test_refuse_nom_vide(client_vierge):
    resp = client_vierge.post(
        "/api/v1/auth/inscription-etablissement",
        json={
            "ecole": "Mon école",
            "nom": "   ",
            "email": "etab.nomvide@exemple.com",
            "password": "Secret123!",
        },
    )
    assert resp.status_code == 422, resp.text


def test_le_verrou_prime_sur_les_controles_de_forme(client):
    """Établissement configuré : même une saisie invalide reçoit le refus de la porte."""
    resp = client.post(
        "/api/v1/auth/inscription-etablissement",
        json={"ecole": "X", "nom": "", "email": "pas-un-email", "password": "1"},
    )
    assert resp.status_code == 409, resp.text


# ---------------------------------------------------------------------------
# Drapeau d'affichage : /auth/options → `etablissement_ouvert`
# Le front s'en sert pour masquer l'onglet « Établissement » (formulaire qui
# mènerait sinon à un 409), et ne le proposer qu'au tout premier démarrage.
# ---------------------------------------------------------------------------
def test_options_ouvre_l_onglet_sur_une_base_vierge(client_vierge):
    """Déploiement neuf : le front doit proposer l'inscription de l'école."""
    resp = client_vierge.get("/api/v1/auth/options")
    assert resp.status_code == 200, resp.text
    assert resp.json()["etablissement_ouvert"] is True


def test_options_ferme_l_onglet_des_que_l_ecole_existe(client):
    """Base de démonstration : le front doit masquer l'onglet « Établissement »."""
    resp = client.get("/api/v1/auth/options")
    assert resp.status_code == 200, resp.text
    assert resp.json()["etablissement_ouvert"] is False


def test_options_bascule_apres_le_bootstrap(client_vierge):
    """Après le bootstrap, le drapeau retombe tout seul : plus d'onglet proposé."""
    ouvert = client_vierge.get("/api/v1/auth/options").json()
    assert ouvert["etablissement_ouvert"] is True

    cree = client_vierge.post(
        "/api/v1/auth/inscription-etablissement", json=_corps("direction@exemple.com")
    )
    assert cree.status_code == 201, cree.text

    ferme = client_vierge.get("/api/v1/auth/options").json()
    assert ferme["etablissement_ouvert"] is False


def test_inscription_parent_refuse_toujours_role_admin(client):
    """La porte Parent ne crée jamais de compte Administrateur."""
    email = "parent.eco@exemple.com"
    resp = client.post(
        "/api/v1/auth/inscription",
        json={"nom": "Parent École", "email": email, "password": "Secret123!"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["user"]["role"] == "Parent"
