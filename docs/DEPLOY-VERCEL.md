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
- `.vercelignore` (racine) → exclut du téléversement les secrets (`.env*`),
  données locales, tests et `.venv` (aucun `vercel.json` requis).
- ⚠️ Le projet Vercel doit avoir le **Framework Preset = Python** (Settings →
  General du projet, ou API `PATCH /v9/projects/{id}` `{"framework":"python"}`).
  Sans cela, Vercel déploie le dossier en **statique** : le front s'affiche mais
  toutes les routes `/api/*` renvoient 404 (aucun runtime Python).
- `backend/_init_pg.py` → initialisation NON destructive de la base cible
  (tables manquantes + compte admin) avant la mise en production.

## 1. Créer le projet Supabase (gratuit)

1. Aller sur https://supabase.com → **Start your project** (connexion GitHub
   ou e-mail).
2. Créer une **New project** : nom `schoolapp`, mot de passe base (à garder),
   région proche (ex. `West US` / `eu-central-1`).
3. Une fois créé : **Project Settings → Database → Connection string**.
   Copier l'URI **directe** affichée par le dashboard (onglet *Direct
   connection*, port 5432) :
   `postgresql://postgres.<ref>:<mdp>@aws-1-<region>.pooler.supabase.com:5432/postgres`
   (la génération du pooler peut être `aws-0` **ou** `aws-1` ; le dashboard
   fournit toujours la bonne URI — le vieux domaine `db.<ref>.supabase.co`
   n'existe plus).
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
vercel link        # associe le dossier au projet « schoolapp »
vercel env add DATABASE_URL production   # coller l'URL Supabase (secret, jamais affiché)
vercel env add SECRET_KEY production     # coller une longue chaîne aléatoire
vercel deploy --prod
```

Puis `vercel env add` éventuellement pour `preview` / `development`.
Après le déploiement : ouvrir **l'alias de production** (affiché par le CLI,
ici `https://schoolapp-flame-six.vercel.app`) et se connecter avec
`admin@lesavoir.edu` / `Savoir2026!`.

> **URLs de déploiement vs domaine de production** : sur le plan Hobby, la
> protection d'accès Vercel (Vercel Authentication) s'applique aux URLs de
> déploiement temporaires `*-<hash>-<scope>.vercel.app` (page « Login –
> Vercel ») — c'est **normal**. L'alias de production (`schoolapp-*.vercel.app`
> ou le domaine personnalisé) reste **public** : c'est celui à diffuser.

## Rappels

- Vérifier en local avant chaque déploiement : `.venv\Scripts\python.exe -X utf8 -m pytest` dans `backend/`.
- Modifier le mot de passe admin depuis **Réglages** après la 1re connexion.
- Toute variable secrète (DATABASE_URL, SECRET_KEY) passe par
  `vercel env add` ou le dashboard Vercel — jamais par git ni par le code.
- Vérifier un déploiement : `curl https://<alias>/api/v1/health` doit répondre
  `{"status":"ok",...}`. Un 404 sur `/api/v1/*` = framework preset non réglé
  sur Python (voir Architecture).
