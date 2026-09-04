"""Configuration des tests — base SQLite dédiée (backend/data/test_school.db).

Importante : la variable DB_NAME doit être positionnée AVANT tout import de
`app.config` (le cache settings est construit au premier import).
"""

from __future__ import annotations

import os

os.environ.setdefault("DB_NAME", "test_school.db")
# Les tests pytest exercent l'API sur le jeu de démonstration déterministe :
# on force seed_demo=True (l'application normale démarre, elle, sans seed).
os.environ.setdefault("SEED_DEMO", "1")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


# Base de test éphémère : supprimée avant la session pour garantir un seed
# frais et déterministe à chaque exécution.
_TEST_DB = os.path.join(os.path.dirname(__file__), "..", "data", "test_school.db")
if os.path.exists(_TEST_DB):
    os.remove(_TEST_DB)


@pytest.fixture(scope="session")
def client():
    from app.main import app

    with TestClient(app) as c:  # déclenche lifespan (init + seed)
        yield c


@pytest.fixture(scope="session")
def admin_token(client: TestClient) -> str:
    resp = client.post("/api/v1/auth/login", json={"email": "admin@lesavoir.edu", "password": "Savoir2026!"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def auth(client: TestClient, email: str) -> str:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": "Savoir2026!"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
