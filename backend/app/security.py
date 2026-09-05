"""Sécurité — hachage des mots de passe (PBKDF2, stdlib) et JWT (PyJWT)."""

from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt

from app.config import settings

# ---------------------------------------------------------------------------
# Hachage des mots de passe (PBKDF2-HMAC-SHA256 — pas de dépendance externe)
# ---------------------------------------------------------------------------
_ITERATIONS = 240_000


def hash_password(password: str) -> str:
    """Retourne une chaîne encodée  pbkdf2_sha256$itérations$sel$hash."""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return f"pbkdf2_sha256${_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Vérifie un mot de passe contre la chaîne encodée. Tolérant au format."""
    try:
        algo, iters, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iters),
        )
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Jetons JWT
# ---------------------------------------------------------------------------
def create_access_token(
    subject: str, extra: dict | None = None, expire_minutes: int | None = None
) -> str:
    """Crée un JWT signé contenant sub=id utilisateur + informations annexes."""
    duree = expire_minutes or settings.access_token_expire_minutes
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(minutes=duree),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> dict:
    """Décode et valide un JWT ; lève jwt.PyJWTError si invalide/expiré."""
    return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])


# ---------------------------------------------------------------------------
# Codes de vérification par email (connexion sans mot de passe)
# ---------------------------------------------------------------------------
def hasher_code_verification(code: str) -> str:
    """Hache un code avec la SECRET_KEY (HMAC-SHA256) avant stockage."""
    return hmac.new(
        settings.secret_key.encode("utf-8"), code.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def verifier_code_verification(code: str, stocke: str) -> bool:
    """Compare en temps constant un code saisi au code haché stocké."""
    if not code or not stocke:
        return False
    return hmac.compare_digest(hasher_code_verification(code), stocke)
