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

## Migrer une base existante (isolation multi-établissements)

Deux scripts selon le moteur — les deux **refusent de s'exécuter deux fois** et
ne touchent jamais aux identifiants métier (codes `3A`, `S1`, `T001`, `EL001`…).

| Base | Script | Méthode |
|---|---|---|
| SQLite (développement) | `_migrate_school_id.py` | reconstruction des tables + sauvegarde `data/school.db.bak-<horodatage>` |
| PostgreSQL (production) | `_migrate_school_id_pg.py` | **en place**, transaction unique, aucune reconstruction |

```powershell
# PostgreSQL : simulation d'abord (aucune écriture), puis application réelle
$env:DATABASE_URL = 'postgresql://utilisateur:motdepasse@hote:5432/base'
.venv\Scripts\python.exe -X utf8 _migrate_school_id_pg.py
.venv\Scripts\python.exe -X utf8 _migrate_school_id_pg.py --appliquer
```

Le script PostgreSQL contrôle la parité de schéma avec les modèles **avant**
(colonnes, base non déjà migrée) et **après** (comptage table par table, aucune
ligne perdue, PK/FK/UNIQUE composites conformes, `membres` et
`membres_invitations` créées) : toute différence annule la transaction.
Il doit être exécuté **avant** le déploiement du code Phase 2 / Phase 3, sinon
les routes de domaine échouent sur `no such column: school_id`.

### Appliquer au serveur de production (Supabase)

> **Le plan gratuit Supabase ne comporte aucune sauvegarde automatique** :
> la sauvegarde manuelle ci-dessous est la **seule** marche arrière possible.
> Elle n'est pas facultative.

Le pilotage se fait par un script qui enchaîne les étapes dans l'ordre imposé —
sauvegarde, **contrôle de la sauvegarde**, simulation, confirmation, migration —
et s'arrête au moindre doute :

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -X utf8 _migrer_prod_supabase.py
```

Il demande la chaîne de connexion en saisie masquée (jamais écrite sur le
disque) ; si `$env:DATABASE_URL` est déjà définie, il la reprend. Pour écrire
la sauvegarde ailleurs que dans `Documents\sauvegardes-saint-collete` :

```powershell
.\.venv\Scripts\python.exe -X utf8 _migrer_prod_supabase.py --dossier D:\sauvegardes
```

La migration réelle n'est déclenchée qu'en tapant `MIGRER` en majuscules.
**Juste après**, déployer sans attendre — l'ancien code reste toutefois
compatible (les `school_id` créés ont une valeur par défaut), donc il n'y a pas
d'interruption de service entre les deux.

#### Marche arrière

Les trois fichiers produits par la sauvegarde (`01-schema.sql`,
`02-donnees.sql`, `03-roles.sql`) se restaurent avec `psql` dans une base
**vide** — **jamais** par-dessus la base en service :

```powershell
$d = 'C:\Users\USER\Documents\sauvegardes-saint-collete\<horodatage>'
psql $env:RESTAURE_URL -v ON_ERROR_STOP=1 -f "$d\01-schema.sql"
psql $env:RESTAURE_URL -v ON_ERROR_STOP=1 -f "$d\02-donnees.sql"
```

Deux particularités à connaître :

- le dump de données commence par `SET session_replication_role = replica`, ce
  qui neutralise les clés étrangères pendant la restauration : l'ordre des
  tables n'a pas d'importance ;
- il contient aussi `SET transaction_timeout = 0` (paramètre apparu avec
  PostgreSQL 17). Sur un serveur **16 ou antérieur**, `psql` s'arrête sur
  `unrecognized configuration parameter "transaction_timeout"` : retirez cette
  ligne, ou relancez sans `ON_ERROR_STOP`.

Ces deux points ont été vérifiés sur un bac à sable : sauvegarde de 748 lignes
sur 20 tables, restaurée à l'identique (codes de sortie 0, comptages égaux).

## Principaux points d'entrée

| Méthode & chemin | Rôle | Description |
|---|---|---|
| `POST /api/v1/auth/login` | public | Connexion → jeton JWT |
| `GET /api/v1/auth/me` | connecté | Profil courant |
| `GET /api/v1/health` | public | État du service — compteurs et nom d'établissement **uniquement si un jeton valide** est fourni |
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
