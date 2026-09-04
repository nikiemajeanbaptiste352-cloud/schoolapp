"""Schémas Pydantic — validation des entrées/sorties de l'API.

Les formes renvoyées reflètent volontairement celles attendues par le front
(js/*.js) afin de rendre la bascule d'intégration transparente.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Authentification
# ---------------------------------------------------------------------------
class LoginIn(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    """Profil utilisateur exposé (jamais de password_hash)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    role: str
    nom: str
    actif: bool = True
    eleve_id: str | None = None
    enseignant_id: str | None = None
    parent_id: int | None = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
    ecole: str | None = None
    annee: str | None = None


# ---------------------------------------------------------------------------
# École / informations publiques
# ---------------------------------------------------------------------------
class EcoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nom: str
    sigle: str
    slogan: str
    annee: str
    devise: str
    telephone: str
    email: str
    adresse: str
    version: str


class MessageOut(BaseModel):
    message: str
