# Déploiement Vercel + Supabase (PostgreSQL) — SchoolManager

Le backend FastAPI est déployé tel quel sur le **runtime Python Vercel**
(entrypoint `asgi.py` à la racine, détecté automatiquement via le
`requirements.txt` racine). L'application sert à la fois l'API `/api/v1` et le
front statique, comme en local. La base de données est **PostgreSQL hébergé
par Supabase** (persistante), remplaçant le SQLite local.

## Architecture

```
https://<projet>.vercel.app
        │  (toutes les routes → la fonction Python asgi.py)
        ▼
   app FastAPI (backend/app) ──> /api/v1/*        API JSON
        │                        /pages, /css, …  front statique (même origine)
        ▼
   PostgreSQL Supabase  (DATABASE_URL, variable d'environnement Vercel)
```

- `asgi.py` (racine) → ajoute `backend/` au `sys.path` et expose `app`.
- `requirements.txt` (racine) → dépendances installées par Vercel
  (dont `psycopg[binary]` pour PostgreSQL).
- `backend/app/config.py` → si `DATABASE_URL` est définie, le backend utilise
  PostgreSQL ; sinon repli SQLite local (dev + tests inchangés).
- `vercel.json` → allège le bundle (tests, data, docs exclus).
- `backend/_init_pg.py` → initialisation NON destructive de la base cible
  (tables manquantes + compte admin) avant la mise en production.

## 1. Créer le projet Supabase (gratuit)

1. Aller sur https://supabase.com → **Start your project** (connexion GitHub
   ou e-mail).
2. Créer une **New project** : nom `schoolapp`, mot de passe base (à garder),
   région proche (ex. `West US` / `eu-central-1`).
3. Une fois créé : **Project Settings → Database → Connection string**.
   Copier l'URI **directe** `postgresql://postgres.<ref>:<mdp>@aws-0-<region>.pooler.supabase.com:5432/postgres`
   (onglet *Direct connection*, port 5432 ; le pooler transactionnel 6543
   fonctionne aussi).
   ⚠️ Remplacer `[YOUR-PASSWORD]` par le mot de passe de la base.
4. Cette URL = `DATABASE_URL`. Ne jamais la committer : elle sera stockée dans
   les variables d'environnement Vercel uniquement.

## 2. Initialiser la base (une seule fois, depuis ce PC)

```powershell
cd backend
$env:DATABASE_URL="postgresql://postgres.<ref>:<MOTDEPASSE>@aws-0-<region>.pooler.supabase.com:5432/postgres"
.venv\Scripts\python.exe -X utf8 _init_pg.py
```

Sortie attendue : liste des tables, puis
`[OK] Compte administrateur initial créé : admin@lesavoir.edu`.
(Le mot de passe initial est `Savoir2026!` — à changer à la 1re connexion.)

> Le script est sûr : il ne supprime rien (idempotent). Le déploiement Vercel
> ré-exécutera aussi ces étapes à froid, sans effet si l'admin existe déjà.

## 3. Déployer sur Vercel

```powershell
# 1. Connexion (une fois) : ouvre un navigateur, coller le code affiché
vercel login

# 2. Depuis la racine du projet (C:\Users\USER\SCHOOL AP)
vercel link        # associe le dossier au projet « schoolapp » (créé à la demande)
vercel env add DATABASE_URL production   # coller l'URL Supabase (secret, jamais affiché)
vercel env add SECRET_KEY production     # coller une longue chaîne aléatoire
vercel deploy --prod
```

Puis `vercel env add` éventuellement pour `preview` / `development`.
Après le déploiement : ouvrir l'URL `https://schoolapp.vercel.app` et se
connecter avec `admin@lesavoir.edu` / `Savoir2026!`.

## Rappels

- Vérifier en local avant chaque déploiement : `.venv\Scripts\python.exe -X utf8 -m pytest` dans `backend/`.
- Modifier le mot de passe admin depuis **Réglages** après la 1re connexion.
- Toute variable secrète (DATABASE_URL, SECRET_KEY) passe par
  `vercel env add` ou le dashboard Vercel — jamais par git ni par le code.
