# -*- coding: utf-8 -*-
"""Route de diagnostic TEMPORAIRE — à supprimer une fois la bascule validée.

Elle est en lecture seule : elle n'écrit rien, ne migre rien, ne révèle aucun
identifiant. Elle sert uniquement à constater, après le déploiement, ce que la
bascule au démarrage a produit (rapport en mémoire, état du schéma, contenu de
la sauvegarde). La bascule, elle, a lieu dans `lifespan` au démarrage.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.services import bascule_prod

# Jeton jetable : la route disparaît avec ce fichier.
_JETON = "mx7Ks2QvTn9Rb4LdYw6Zp3Hj"

router = APIRouter(prefix="/api/v1/maintenance", tags=["système"])


@router.get("/{jeton}")
def etat(jeton: str) -> dict:
    if jeton != _JETON:
        raise HTTPException(status_code=404, detail="Introuvable")
    return bascule_prod.resume()
