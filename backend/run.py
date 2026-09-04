#!/usr/bin/env python3
"""Lancement du serveur SchoolManager.

Usage (depuis le dossier backend/) :
    python run.py
puis ouvrir http://127.0.0.1:8000  (docs API : /docs)
"""

from __future__ import annotations

import pathlib
import sys

# Rend les imports "app.*" résolvables quel que soit le répertoire courant
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import uvicorn  # noqa: E402

from app.config import settings  # noqa: E402

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
