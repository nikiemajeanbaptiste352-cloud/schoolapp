# SchoolManager — Backend (API REST)

API FastAPI + SQLite de gestion scolaire. Elle sert également le front-end
statique (mêmes chemins relatifs).

La page de connexion (`/`) utilise l'API réelle : le rôle et le nom affichés
sont ceux renvoyés par le serveur (jeton JWT stocké en `sessionStorage`).
Connecté, le front charge **un instantané unique de toutes les données** via
`GET /api/v1/etat` (fabrique `construireSD`) : les 12 pages affichent donc les
données réellement présentes dans la base.

> **Mode données réelles (défaut)** : au démarrage, la base est **vide** —
> aucune donnée fictive n'est insérée. Seul le **compte administrateur
> initial** est créé s'il n'existe encore aucun utilisateur. Le jeu de
> démonstration (ancien seed) n'est injecté que si la variable d'environnement
> `SEED_DEMO=1` est positionnée (utilisée par pytest uniquement).

> **Portée actuelle** : seules les lectures sont branchées sur l'API. Les
> écritures des pages (élèves, notes, paiements, annonces, réglages) restent
> **en mémoire** (elles mutent l'instantané `window.SD` et sont perdues au
> rechargement) — la persistance des écritures est une évolution suivante.
> Pour charger vos données réelles : remplissez directement `backend/data/school.db`
> (les tables sont documentées dans `app/models.py`).

## Démarrage

```powershell
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python run.py
```

Puis ouvrir :

- Application front : <http://127.0.0.1:8000>
- Documentation interactive (Swagger) : <http://127.0.0.1:8000/docs>

### Configuration

Copier `backend/.env.example` vers `backend/.env` pour personnaliser la clé
secrète JWT, le port, etc. Sans `.env`, les valeurs par défaut s'appliquent
(dont une clé de développement — à changer en production).

## Compte administrateur initial

Base vierge (mode données réelles) : le backend crée automatiquement, au
premier démarrage, le compte administrateur suivant :

| Rôle | Email | Mot de passe initial |
|---|---|---|
| Administrateur | `admin@lesavoir.edu` | `Savoir2026!` |

> Changez ces identifiants (table `users`, mot de passe haché avec
> `app/security.hash_password`) une fois vos données importées.

Les autres comptes (professeurs, élèves, parents) sont créés par
l'établissement selon ses besoins ; le mot de passe d'un utilisateur se règle
dans la table `users` (hash PBKDF2 via `app/security.py`).

## Réinitialiser la base

Pour repartir d'une base **totalement vide** (tables recréées + seul compte
administrateur initial) :

```powershell
.venv\Scripts\python.exe -X utf8 _reset_db.py
```

## Principaux points d'entrée

| Méthode & chemin | Rôle | Description |
|---|---|---|
| `POST /api/v1/auth/login` | public | Connexion → jeton JWT |
| `GET /api/v1/auth/me` | connecté | Profil courant |
| `GET /api/v1/health` | public | État + compteurs du seed |
| `GET /api/v1/ecole`, `PUT` | admin | École |
| `GET /api/v1/classes`, `/classes/{id}` | connecté | Classes + détail |
| `GET /api/v1/classes/{id}/emploi-du-temps` | connecté | Emploi du temps |
| `GET /api/v1/classes/{id}/bulletins` | connecté | Bulletins (1er trim.) |
| `GET /api/v1/matieres`, `/enseignants` | connecté | Référentiels |
| `GET /api/v1/eleves/`, `POST`, `GET/PUT/DELETE /{id}` | selon rôle | Élèves + fiche |
| `GET/PUT /api/v1/notes`, `/notes/stats` | admin/prof | Notes & stats |
| `GET /api/v1/eleves/{id}/presences`, `POST /api/v1/presences` | selon rôle | Présences |
| `GET /api/v1/paiements`, `/stats`, `POST /paiements/{id}/versements` | admin | Finance |
| `GET /api/v1/dashboard` | connecté | Agrégats du tableau de bord |
| `GET /api/v1/etat` | connecté | **Instantané complet** (école, classes, matières, enseignants, élèves, notes, présences, paiements, annonces) — alimente les 12 pages via `js/live.js` |
| `GET/POST/PUT/DELETE /api/v1/annonces` | public/admin | Annonces |

Les écritures (création élève, encaissement, annonces, notes…) sont réservées
aux rôles appropriés. Le périmètre de lecture est réduit pour Élève (sa fiche)
et Parent (ses enfants).

## Tests

```powershell
cd backend
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest
```

Les tests utilisent une base dédiée `backend/data/test_school.db`,
**supprimée puis re-semée à chaque exécution** (`SEED_DEMO=1`, résultats
déterministes). Ils vérifient la **parité** des résultats (bulletin de la 3e A,
moyenne/classement d'EL001, emploi du temps, effectifs) ainsi que le respect
des permissions par rôle.

## Architecture

```
backend/
├─ app/
│  ├─ config.py      # paramètres (.env, chemins front/backend)
│  ├─ database.py    # moteur + session SQLAlchemy
│  ├─ models.py      # modèle relationnel (miroir de window.SD)
│  ├─ seed.py        # seed de démo optionnel (SEED_DEMO=1, tests) + bootstrap admin
│  ├─ security.py    # hash PBKDF2 + JWT
│  ├─ auth.py        # dépendances FastAPI (jeton, rôles)
│  ├─ schemas.py     # DTO Pydantic
│  ├─ main.py        # application FastAPI + montage du front
│  ├─ routers/       # ecole, referentiel, eleves, pedagogie, presences, paiements, dashboard, etat, auth
│  └─ services/sd.py # calculs de parité (moyennes, rangs, EDT…)
├─ tests/            # pytest (parité, permissions)
├─ data/             # base SQLite (créée au premier lancement)
├─ requirements.txt
└─ run.py
```
