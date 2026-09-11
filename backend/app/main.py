"""Application FastAPI — SchoolManager.

- API REST versionnée sous /api/v1
- Serrure d'authentification JWT (Phase 2)
- Le front statique (index.html, pages/, css/, js/, assets/) est servi
  depuis la racine : les chemins relatifs du front sont conservés.

Ordre des routes important : l'API est déclarée AVANT le montage statique "/".
"""

from __future__ import annotations

from contextlib import asynccontextmanager
import mimetypes
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.config import FRONT_DIR, settings
from app.database import SessionLocal, init_db
from app.models import Annonce, Classe, Ecole, Eleve, Enseignant, Matiere, User
from app.routers import (
    auth as auth_router,
    dashboard as dashboard_router,
    ecole as ecole_router,
    eleves as eleves_router,
    etat as etat_router,
    membres as membres_router,
    paiements as paiements_router,
    paie as paie_router,
    pedagogie,
    presences as presences_router,
    referentiel,
)
from app.security import decode_token
from app.seed import seed_all, seed_bootstrap, seed_users
from app.services import bascule_prod, sd
from app.services.membres import assurer_membres


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Conversion ponctuelle du schéma de production (Phase 2 + 3), AVANT tout
    # accès aux modèles : sans données migrées, `create_all` ne comble pas les
    # colonnes manquantes et les requêtes échoueraient. Sans effet sur une base
    # déjà convertie ou sur la base locale.
    bascule_prod.executer_si_necessaire()

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
        # Phase 3 — rattachement : matérialise `membres` pour les identités
        # déjà rattachées (`users.school_id`). Idempotent et sans effet si la
        # table est déjà remplie.
        assurer_membres(db)
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


async def _contexte_ecole_par_jeton(request: Request, call_next):
    """Pose le contexte école (Phase 2) à partir du jeton Bearer.

    Indispensable : les dépendances synchrones (`get_current_user`) et les
    endpoints synchrones s'exécutent dans des threads de travail distincts ;
    un ContextVar posé dans la dépendance ne serait pas visible dans le corps
    de l'endpoint. Ici, le contexte est posé dans la tâche ASGI de la requête,
    puis copié dans chaque thread de travail lancé ensuite — l'isolation par
    `school_id` est donc fiable pour toutes les routes (publiques incluses,
    quand un jeton est fourni).

    Les jetons invalides sont ignorés silencieusement : l'authentification
    stricte reste gérée par les dépendances des routeurs.
    """
    entete = request.headers.get("authorization", "")
    if entete.lower().startswith("bearer "):
        jeton = entete[7:].strip()
        try:
            sub = decode_token(jeton).get("sub")
            if sub is not None:
                db = SessionLocal()
                try:
                    utilisateur = db.get(User, int(sub))
                    if utilisateur is not None:
                        sd.definir_ecole_courante(utilisateur.school_id)
                finally:
                    db.close()
        except Exception:
            pass  # jeton illisible → aucun contexte école (fail-closed).
    try:
        return await call_next(request)
    finally:
        sd.definir_ecole_courante(None)


app.add_middleware(BaseHTTPMiddleware, dispatch=_contexte_ecole_par_jeton)


# ---------------------------------------------------------------
# Santé / vérification du seed
# ---------------------------------------------------------------
@app.get("/api/v1/health", tags=["système"])
def health() -> dict:
    """Sonde de disponibilité.

    Appelée sans jeton, elle n'expose que l'état du service : ni nom
    d'établissement, ni compteurs (aucune fuite inter-écoles). Les compteurs
    ne sont renvoyés que si un jeton valide a posé le contexte école.
    """
    db = SessionLocal()
    try:
        sid = sd.ecole_courante()
        counts = None
        ecole_nom = None
        if sid is not None:
            counts = {
                "classes": db.scalar(
                    select(func.count(Classe.id)).where(Classe.school_id == sid)
                ),
                "matieres": db.scalar(
                    select(func.count(Matiere.id)).where(Matiere.school_id == sid)
                ),
                "enseignants": db.scalar(
                    select(func.count(Enseignant.id)).where(Enseignant.school_id == sid)
                ),
                "eleves": db.scalar(
                    select(func.count(Eleve.id)).where(Eleve.school_id == sid)
                ),
                "annonces": db.scalar(
                    select(func.count(Annonce.id)).where(Annonce.school_id == sid)
                ),
            }
            ecole_nom = db.scalar(
                select(Ecole.nom).where(Ecole.id == sid).limit(1)
            )
    finally:
        db.close()
    return {
        "status": "ok",
        "base": settings.db_name,
        "ecole": ecole_nom,
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
    paie_router.router,
    membres_router.router,
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


# Téléchargement de l'application Android depuis le site (dossier « telecharger/ »).
# Sans cette déclaration, le type MIME de « .apk » n'est pas toujours connu du
# système (surtout sous Linux) : Starlette retomberait sur `text/plain` et le
# navigateur afficherait des caractères illisibles au lieu de télécharger le
# fichier. Déclaration explicite = comportement identique partout.
mimetypes.add_type("application/vnd.android.package-archive", ".apk")

app.mount("/", FrontStatic(directory=str(FRONT_DIR), html=True), name="front")
