# Plan d'implantation — Backend SchoolManager

> Objectif : transformer l'application front **100 % démo / en mémoire** en
> application **client-serveur persistée** (Python **FastAPI** + **SQLite**),
> en conservant à l'identique l'interface, les données et les résultats
> (bulletins, classements, emplois du temps) du front actuel.

## Architecture cible

```
backend/
├── requirements.txt          # Dépendances runtime
├── requirements-dev.txt      # pytest, httpx
├── run.py                    # Lancement uvicorn + init DB
├── .env.example              # SECRET_KEY, TTL token…
├── app/
│   ├── config.py             # Réglages (.env + chemins)
│   ├── database.py           # Engine SQLite + session + Base
│   ├── models.py             # Modèles SQLAlchemy (parité SD)
│   ├── schemas.py            # DTO Pydantic (miroir des objets SD)
│   ├── security.py           # Hash mots de passe (pbkdf2), JWT
│   ├── auth.py               # Dépendances rôles (get_current_user…)
│   ├── seed.py               # Données = ancien window.SD (idempotent)
│   ├── services/             # Moteur métier (bulletins, EDT, stats)
│   ├── routers/              # eleves, enseignants, notes, …
│   └── main.py               # App FastAPI : API + front statique
└── tests/                    # pytest (parité des agrégats, droits)
```

## Tables SQL (parité avec `js/data.js`)

| Table | Clé | Notes |
|---|---|---|
| `ecole` | id | singleton — nom, sigle, slogan, annee, devise, tel, email, adresse, version |
| `classes` | **id (ex. `3A`)** | nom, cycle, salle, `principal_id`→enseignants |
| `matieres` | **id (`S1`…)** | nom, coef, icone, couleur |
| `classe_matiere` | PK composite | programme par classe (`ordre`) — Collège/Lycée |
| `enseignants` | **id (`T001`)** | nom, prenom, sexe, tel, email, `matiere_id`, statut |
| `enseignant_classe` | PK composite | affectation M:N des classes |
| `parents` | id auto | nom, lien, tel, email, profession, adresse |
| `eleves` | **id (`EL001`)** | nom, prenom, sexe, naissance, `classe_id`, statut, inscription, `parent_id` |
| `notes` | id auto | eleve_id, matiere_id, eval, note (0→20, pas 0,5) |
| `presences` | id auto | eleve_id, date, statut P/R/A |
| `paiements` | id auto | eleve_id, motif, total |
| `versements` | id auto | paiement_id, montant, date, mode |
| `annonces` | **id (`A1`…)** | titre, contenu, categorie, date, auteur, important |
| `users` | id auto | email unique, hash, rôle, liaison eleve/parent/enseignant |

## API REST — `/api/v1`

- `POST /auth/login`, `GET /auth/me` → JWT Bearer
- `GET|PUT /ecole`
- `GET|POST /eleves`, `GET|PUT|DELETE /eleves/{id}`, `GET /eleves/{id}/bulletin`
- `CRUD /enseignants`, `GET|POST /classes`, `GET /classes/{id}`, `GET /classes/{id}/emploi-du-temps`
- `GET /matieres`
- `GET|PUT /notes`, `GET /notes/stats`
- `GET|POST /presences`
- `GET|POST /paiements`, `POST /paiements/{id}/versements`
- `CRUD /annonces`
- `GET /stats/resume` (dashboard)
- `GET /etat` → **instantané complet** consommé par les pages (voir Phase 9)

## Rôles & permissions

Administrateur (tout) · Professeur (notes restreintes à ses matières/classes,
lecture pédagogique) · Élève (soi-même) · Parent (ses enfants via `parents`).

## Intégration front (Phase 7) — état livré

Le client `js/api.js` (chargé sur toutes les pages et la page de connexion)
fournit l'adaptateur fetch vers `/api/v1` avec jeton Bearer :

- `API.connexion(email, mdp)` → `POST /api/v1/auth/login`, mémorise le jeton
  (`sessionStorage.sm_token`) et le profil (`sm_user`) ;
- `API.deconnexion()` / `API.profil()` / `API.aUnJeton()` / `API.disponible()` ;
- méthodes métier alignées 1:1 sur les routes backend (`eleves`, `bulletins`,
  `notes`, `paiements`, `annonces`, `emploiDuTemps`, `tableauDeBord`, …).

**Connexion réelle** : la page de connexion interroge l'API ; le rôle affiché
est celui renvoyé par le serveur (source de vérité), les erreurs HTTP
(401/403) sont affichées en français.

**Pas de mode démonstration** : si l'application est ouverte en `file://`
(hors backend) ou si le serveur est injoignable, le front affiche un écran
« démarrez le serveur » — aucune donnée fictive n'existe plus côté client ni
côté serveur (les comptes de rôle pré-remplis et le repli « n'importe quel
email/mot de passe » ont été supprimés).

**Périmètre data des pages** : les pages conservent `window.SD`
(lectures synchrones). La **parité** entre `SD` et l'API est verrouillée par
les tests pytest (bulletins 3A, moyennes/classement, emploi du temps,
effectifs) : basculer une page de `SD` vers `API.xxx()` ne changera donc aucun
chiffre affiché.

## Données vivantes des pages (Phase 9) — état livré

Les 12 pages affichent désormais les **données de l'API** (et non plus les
tableaux de démonstration) lorsqu'elles sont servies par le backend avec une
session connectée.

- `GET /api/v1/etat` (auth Bearer, tout rôle connecté) renvoie un instantané
  unique aux formes attendues par le front : `ecole`, `classes` (avec
  `principal`), `matieres`, `enseignants`, `eleves` (avec `classe` et
  `parent`), `notes`, `presences`, `paiements` (versements), `annonces`.
  Le backend démarre avec une **base vide** (SEED_DEMO non positionné) ; le
  jeu de démonstration n'est réinjecté que par `SEED_DEMO=1` (pytest).
- `js/live.js` (nouveau chargeur, dernière balise de chaque page) : si un
  jeton est présent (`sessionStorage.sm_token`) et l'API joignable, il charge
  `/etat` en XHR **synchrone** puis reconstruit `window.SD` via la fabrique
  `construireSD(d)` de `js/data.js` — les scripts de pages et leur logique de
  rendu restent **inchangés** (`window.SM_MODE = "api"`, pastille « API »).
- **Sans serveur** : `file://` ou serveur injoignable → écran « démarrez le
  serveur » (aucune donnée fictive) ; jeton absent/expiré (401) → retour à la
  page de connexion.
- Tests pytest dédiés : authentification requise sur `/etat` + forme/compteurs
  de l'instantané (`test_parite.py`, 12/12).

> **Portée** : lectures seules branchées sur l'API. Les écritures des pages
> (ajout élève, encaissement, annonce, note, paramètres) mutent encore
> l'instantané **en mémoire** et ne sont **pas persistées** — c'est l'étape
> suivante (POST/PUT réels pilotés par les formulaires existants).

## Ordre d'exécution

0. Socle FastAPI + SQLite + health + montage front ✅
1. Modèles SQLAlchemy + seed de parité ✅
2. Auth (comptes + JWT + rôles) ✅
3. CRUD École/Élèves/Enseignants/Classes/Matières/Annonces ✅
4. Notes + statistiques + moyennes/classement ✅
5. Présences + Paiements ✅
6. Bulletins + Emploi du temps + Dashboard ✅
7. Intégration front (`js/api.js` + connexion réelle) ✅
8. Tests (pytest 10/10, base régénérée à chaque exécution) + E2E navigateur ✅
9. Pages sur données vivantes (`/api/v1/etat` + `js/live.js` + `construireSD`, repli démo supprimé) ✅
10. (Suivant) Persistance des écritures des pages (POST/PUT pilotés par les formulaires)

### Validation finale (E2E, serveur `http://127.0.0.1:8000`)

- Index, `css/`, `js/`, `assets/` et les 12 pages servis (HTTP 200, zéro
  erreur console) ; `backend/`, `.env`, fichiers cachés → 404.
- Connexion admin → tableau de bord ; mauvaise mot de passe → message serveur
  français, pas de repli démo ; rôle Élève → profil restreint (lecture de son
  propre dossier).
- Déconnexion : jeton + session effacés, retour à la page de connexion.
- `FrontStatic` refuse `backend/`, `data/`, `tests/`, `docs/` et les fichiers
  cachés (chemins normalisés avant filtrage).

### E2E Phase 9 (navigateur, serveur `http://127.0.0.1:8000`)

- Admin connecté : les **12 pages** se chargent en mode `api` (pastille
  « API ») avec **0 erreur console** ; tableau de bord = compteurs réels de la
  base (base vide : 0 élève / 0 enseignant / 0 classe). Sur la base du seed
  pytest (`SEED_DEMO=1`), la parité des calculs (moyennes, classement,
  bulletins) est verrouillée par les tests.
- Ouverture en `file://` → écran « démarrez le serveur » (aucune donnée
  fictive générée).
- 401 (`/etat` sans jeton) → jeton effacé + retour à la page de connexion.
