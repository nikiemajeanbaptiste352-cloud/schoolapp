"""Point d'entrée ASGI pour Vercel — SchoolManager.

Vercel (runtime Python, preset FastAPI) cherche un fichier asgi.py à la
racine exposant une variable `app`, puis route TOUTES les requêtes vers
cette application : le comportement est identique au serveur local.

Le package importable est `backend/app` ; on ajoute donc backend/ au
sys.path avant d'importer l'application FastAPI (qui sert l'API sous
/api/v1 ET le front statique depuis la racine du projet).
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
for _chemin in (_ROOT, _ROOT / "backend"):
    if str(_chemin) not in sys.path:
        sys.path.insert(0, str(_chemin))

# noqa : import différé volontairement (après la mise à jour du sys.path)
from app.main import app  # noqa: E402,F401
