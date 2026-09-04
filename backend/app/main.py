"""Application FastAPI — SchoolManager.

- API REST versionnée sous /api/v1
- Serrure d'authentification JWT (Phase 2)
- Le front statique (index.html, pages/, css/, js/, assets/) est servi
  depuis la racine : les chemins relatifs du front sont conservés.

Ordre des routes important : l'API est déclarée AVANT le montage statique "/".
"""

from __future__ import annotations

from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select

from app.config import FRONT_DIR, settings
from app.database import SessionLocal, init_db
from app.models import Annonce, Classe, Ecole, Eleve, Enseignant, Matiere
from app.routers import (
    auth as auth_router,
    dashboard as dashboard_router,
    ecole as ecole_router,
    eleves as eleves_router,
    etat as etat_router,
    paiements as paiements_router,
    pedagogie,
    presences as presences_router,
    referentiel,
)
from app.seed import seed_all, seed_bootstrap, seed_users


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Initialisation base (tables SQLite) ; aucune donnée fictive par défaut.
    init_db()
    db = SessionLocal()
    try:
        if settings.seed_demo:
            # Mode démonstration (tests pytest uniquement).
            seed_all(db)
            seed_users(db)
        else:
            # Mode données réelles : base vierge + compte administrateur initial.
            seed_bootstrap(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title="SchoolManager API",
    description="API REST de gestion scolaire (données réelles de l'établissement).",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — utile en développement si le front est ouvert séparément.
# En production, le front étant servi par ce même serveur, inutile de
# restreindre davantage pour une démo ; à durcir en déploiement réel.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------
# Santé / vérification du seed
# ---------------------------------------------------------------
@app.get("/api/v1/health", tags=["système"])
def health() -> dict:
    db = SessionLocal()
    try:
        counts = {
            "ecole": db.scalar(select(func.count(Ecole.id))),
            "classes": db.scalar(select(func.count(Classe.id))),
            "matieres": db.scalar(select(func.count(Matiere.id))),
            "enseignants": db.scalar(select(func.count(Enseignant.id))),
            "eleves": db.scalar(select(func.count(Eleve.id))),
            "annonces": db.scalar(select(func.count(Annonce.id))),
        }
        ecole_nom = db.scalar(select(Ecole.nom).limit(1))
    finally:
        db.close()
    return {
        "status": "ok",
        "ecole": ecole_nom,
        "base": settings.db_name,
        "counts": counts,
    }


# ---------------------------------------------------------------
# Routeurs API (/api/v1/...) — déclarés AVANT le montage statique "/"
# ---------------------------------------------------------------
for _router in (
    auth_router.router,
    referentiel.router,
    ecole_router.router,
    eleves_router.router,
    pedagogie.router,
    presences_router.router,
    paiements_router.router,
    dashboard_router.router,
    etat_router.router,
):
    app.include_router(_router)


# ---------------------------------------------------------------
# Montage du front statique (sécurisé : backend/ et fichiers cachés masqués)
# ---------------------------------------------------------------
class FrontStatic(StaticFiles):
    """StaticFiles qui refuse de servir backend/, data/, tests/, docs/
    et tout fichier ou dossier caché (commençant par un point)."""

    _REJETES = {"backend", "data", "tests", "docs"}

    def lookup_path(self, path: str):  # type: ignore[override]
        # Normalise (ex. ".\\index.html" -> "index.html", "/" -> ".")
        norm = os.path.normpath(path or ".")
        segs = [s for s in norm.replace("\\", "/").split("/") if s and s != "."]
        if segs and (segs[0] in self._REJETES or segs[0].startswith(".")):
            return "", None
        if any(s.startswith(".") for s in segs):
            return "", None
        return super().lookup_path(norm)


app.mount("/", FrontStatic(directory=str(FRONT_DIR), html=True), name="front")
