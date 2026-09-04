# 🎓 SchoolManager

Application web de gestion scolaire (front + API FastAPI + base SQLite).
L'établissement configure ses propres données : **aucune donnée fictive**
n'est incluse — la base démarre vide (seul un compte administrateur initial
est créé, voir `backend/README.md`).

> Interface en français · Devise **FCFA**

## ✨ Fonctionnalités

| Module | Description |
| --- | --- |
| 🔐 **Connexion** | Comptes définis par l'établissement (Administrateur, Professeur, Élève, Parent) — authentification JWT via le backend |
| 🏠 **Tableau de bord** | Statistiques, répartition par classe, derniers paiements, annonces |
| 👨‍🎓 **Élèves** | Liste, recherche, ajout / modification / suppression, fiche détaillée (Notes, Présences, Paiements, Bulletin, Parent) |
| 👨‍🏫 **Enseignants** | Gestion du corps professoral et des classes assignées |
| 🏫 **Classes** | Collège (6ᵉ → 3ᵉ) et Lycée (2nde → Tle), détail par classe |
| 📚 **Matières** | Programmes, coefficients et enseignants |
| 📝 **Notes** | Saisie par classe / matière / évaluation avec statistiques et classement en direct |
| 📊 **Bulletins** | Génération et impression du bulletin (rang, mention, appréciation) |
| 📅 **Emploi du temps** | Grille hebdomadaire par classe, générée automatiquement |
| 💰 **Paiements** | Suivi des frais de scolarité, encaissement, taux de recouvrement |
| 📢 **Annonces** | Publication et suppression de communications |
| ⚙️ **Paramètres** | Identité de l'établissement, session, réinitialisation |

## 📊 Données — serveur uniquement

Connecté au backend, l'application affiche **les données réelles de la base** :
les 12 pages lisent un instantané unique `GET /api/v1/etat`, reconstruit dans
`window.SD` par la fabrique `construireSD` de `js/data.js`.

**Plus aucune donnée fictive** : ouvert en `file://` sans serveur, le front
affiche un écran « démarrez le serveur » ; la connexion hors-ligne avec un
compte fictif a été supprimée.

> **Limite actuelle** : seules les **lectures** sont branchées sur l'API. Les
> modifications faites dans l'interface (élève, note, encaissement, annonce,
> réglages) restent **en mémoire** et sont perdues au rechargement — la
> persistance des écritures est l'étape suivante. Pour charger vos données
> réelles : remplissez directement la base SQLite (voir `backend/README.md`).

## 🗂️ Structure

```
├── index.html            # Page de connexion
├── pages/                # Pages de l'application
├── css/
│   ├── style.css         # Design system
│   ├── responsive.css    # Adaptation mobile / tablette
│   ├── print.css         # Impression du bulletin
│   └── dashboard.css     # Page d'accueil
├── js/
│   ├── api.js            # Adaptateur fetch /api/v1 (jeton Bearer, connexion)
│   ├── data.js           # Fabrique construireSD + données de démo (repli)
│   ├── live.js           # Chargeur : /api/v1/etat → window.SD (mode API)
│   ├── ui.js             # Interface commune (window.SM)
│   └── *.js              # Logique de chaque page
└── assets/logo.svg       # Logo
```

## 🚀 Démarrage

L'application se lance avec le backend (il sert aussi le front) :

```powershell
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python run.py
# Application : http://127.0.0.1:8000
```

La base démarre **vide** : connectez-vous avec le compte administrateur
initial puis importez vos données (voir `backend/README.md`). Ouvrir une page
en `file://` sans le serveur n'affiche **aucune donnée fictive** — un écran
« démarrez le serveur » s'affiche à la place.

## 🖥️ Backend — API REST (FastAPI + SQLite)

Un backend accompagne ce front : API `/api/v1` (auth JWT, CRUD
élèves/classes/notes/annonces, bulletins, emplois du temps, finance) et
serveur du front statique.

```powershell
cd backend
.venv\Scripts\python run.py
# Application : http://127.0.0.1:8000  ·  Docs API : http://127.0.0.1:8000/docs
```

> Compte admin initial : `admin@lesavoir.edu` / `Savoir2026!` (voir `backend/README.md`).

La page de connexion est branchée sur l'API réelle (`js/api.js` — jeton JWT) :
le rôle affiché est celui du serveur. Une fois connecté, `js/live.js` charge
`GET /api/v1/etat` et construit `window.SD` avec **les données réelles de la
base** (`window.SM_MODE = "api"`) ; les écritures restent en mémoire pour
l'instant. Le détail du plan et des validations figure dans
`docs/BACKEND-PLAN.md`.

---
© 2026 SchoolManager — Gestion scolaire
