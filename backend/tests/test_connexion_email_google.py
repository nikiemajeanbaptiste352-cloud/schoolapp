"""Tests de la connexion par code email et de « Se connecter avec Google ».

Le service d'envoi d'emails est neutralisé (monkeypatch) : on capture le code
généré pour pouvoir le rejouer dans la validation. Aucun email réel n'est
envoyé pendant les tests.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app import models
from app.config import settings
from app.database import SessionLocal
from app.services import email as email_service

# Code « fixe » injecté par les tests (au lieu d'un tirage aléatoire).
CODE_FIXE = "424242"


def _activer_email(monkeypatch) -> list[tuple[str, str]]:
    """Active la configuration email et capture les envois."""
    monkeypatch.setattr(settings, "email_from", "SchoolManager <ecole@exemple.com>")
    monkeypatch.setattr(settings, "resend_api_key", "re_test_123")
    monkeypatch.setattr(settings, "smtp_host", "")
    codes_envoyes: list[tuple[str, str]] = []

    def _capture(destinataire: str, code: str) -> None:
        codes_envoyes.append((destinataire, code))

    def _code_fixe(longueur: int | None = None) -> str:
        return CODE_FIXE

    monkeypatch.setattr(email_service, "envoyer_email_code", _capture)
    monkeypatch.setattr(email_service, "generer_code", _code_fixe)
    return codes_envoyes


def _demander(client, email: str, nom: str | None = None):
    return client.post(
        "/api/v1/auth/code/demander",
        json={"email": email, "nom": nom},
    )


# ---------------------------------------------------------------------------
# Options exposées au front
# ---------------------------------------------------------------------------
def test_options_retourne_etat_des_methodes(client):
    """/auth/options liste les méthodes actives (désactivées par défaut)."""
    resp = client.get("/api/v1/auth/options")
    assert resp.status_code == 200
    data = resp.json()
    assert set(data) >= {"google", "code_email"}


# ---------------------------------------------------------------------------
# Demande de code par email
# ---------------------------------------------------------------------------
def test_demander_code_envoie_email_et_indique_delai(client, monkeypatch):
    codes_envoyes = _activer_email(monkeypatch)
    resp = _demander(client, "code.parent@exemple.com", "Code Parent")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["message"]
    assert data["delai"] == 600  # 10 minutes
    assert codes_envoyes == [("code.parent@exemple.com", CODE_FIXE)]


def test_demander_code_exige_email_valide(client, monkeypatch):
    _activer_email(monkeypatch)
    resp = _demander(client, "pas-un-email")
    assert resp.status_code == 422


def test_demander_code_refuse_sans_service_email(client):
    """Sans fournisseur configuré, l'envoi est refusé (503)."""
    resp = _demander(client, "sans.service@exemple.com")
    assert resp.status_code == 503


def test_demander_code_refuse_demande_rapprochee(client, monkeypatch):
    """Deux demandes < 60 s pour le même email → 429 (anti-spam)."""
    _activer_email(monkeypatch)
    email = "anti.spam@exemple.com"
    assert _demander(client, email).status_code == 200
    resp = _demander(client, email)
    assert resp.status_code == 429


# ---------------------------------------------------------------------------
# Validation du code
# ---------------------------------------------------------------------------
def test_valider_code_cree_compte_parent_et_connecte(client, monkeypatch):
    _activer_email(monkeypatch)
    email = "nouveau.code@exemple.com"

    assert _demander(client, email, "Nouveau Code").status_code == 200
    resp = client.post(
        "/api/v1/auth/code/valider",
        json={"email": email, "code": CODE_FIXE, "nom": "Nouveau Code"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["access_token"]
    assert data["user"]["email"] == email
    assert data["user"]["role"] == "Parent"
    assert data["user"]["nom"] == "Nouveau Code"

    # Usage unique : rejouer le même code doit échouer.
    resp2 = client.post(
        "/api/v1/auth/code/valider",
        json={"email": email, "code": CODE_FIXE},
    )
    assert resp2.status_code == 401


def test_valider_code_connecte_compte_existant(client, monkeypatch):
    """Un code valide pour l'email d'un compte existant connecte CE compte."""
    _activer_email(monkeypatch)
    email = "admin@lesavoir.edu"  # compte administrateur existant (seed)

    assert _demander(client, email).status_code == 200
    resp = client.post(
        "/api/v1/auth/code/valider",
        json={"email": email, "code": CODE_FIXE},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["user"]["role"] == "Administrateur"


def test_valider_code_mauvais_code_401(client, monkeypatch):
    _activer_email(monkeypatch)
    email = "mauvais.code@exemple.com"
    assert _demander(client, email).status_code == 200
    resp = client.post(
        "/api/v1/auth/code/valider",
        json={"email": email, "code": "000000"},
    )
    assert resp.status_code == 401


def test_valider_code_expire_401(client, monkeypatch):
    _activer_email(monkeypatch)
    email = "expire.code@exemple.com"
    assert _demander(client, email).status_code == 200

    # On fait expirer le code en base directement.
    with SessionLocal() as db:
        ligne = db.get(models.EmailCode, email)
        assert ligne is not None
        ligne.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            minutes=1
        )
        db.commit()

    resp = client.post(
        "/api/v1/auth/code/valider",
        json={"email": email, "code": CODE_FIXE},
    )
    assert resp.status_code == 401


def test_valider_code_sans_demande_401(client):
    resp = client.post(
        "/api/v1/auth/code/valider",
        json={"email": "jamais.demande@exemple.com", "code": "123456"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Connexion Google (OAuth)
# ---------------------------------------------------------------------------
def test_google_non_configure_503(client):
    resp = client.get("/api/v1/auth/google")
    assert resp.status_code == 503


def test_google_redirige_vers_google_avec_client_id(client, monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "CLIENT_TEST.apps.googleusercontent.com")
    monkeypatch.setattr(settings, "google_client_secret", "SECRET_TEST")
    monkeypatch.setattr(
        settings,
        "google_redirect_uri",
        "http://testserver/api/v1/auth/google/callback",
    )
    resp = client.get("/api/v1/auth/google", follow_redirects=False)
    assert resp.status_code in (302, 307)
    location = resp.headers["location"]
    assert location.startswith("https://accounts.google.com/o/oauth2/v2/auth")
    assert "client_id=CLIENT_TEST" in location
    assert "redirect_uri=" in location
    assert "state=" in location


def test_google_callback_etat_invalide_401(client, monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "CLIENT_TEST.apps.googleusercontent.com")
    monkeypatch.setattr(settings, "google_client_secret", "SECRET_TEST")
    resp = client.get(
        "/api/v1/auth/google/callback",
        params={"code": "xyz", "state": "etat-falsifie"},
    )
    assert resp.status_code == 401
