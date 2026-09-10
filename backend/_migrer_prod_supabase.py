"""Migration de la base PostgreSQL de PRODUCTION (Supabase) — pilotage guidé.

Ce script enchaîne, dans l'ordre imposé, les opérations de la mise à niveau
multi-établissements (Phase 2 + Phase 3) sur la base réelle :

    1. sauvegarde complète (schéma + données + rôles) dans un dossier horodaté ;
    2. contrôle de la sauvegarde (fichiers non vides, données présentes) ;
    3. SIMULATION de la migration par `_migrate_school_id_pg.py` (n'écrit rien) ;
    4. confirmation explicite de l'opérateur ;
    5. migration réelle, puis contrôles automatiques.

Il ne contient aucun secret : la chaîne de connexion est demandée de façon
masquée au clavier, à chaque exécution, et n'est jamais écrite sur le disque.

Pourquoi ce script plutôt que des commandes manuelles :

- l'URL Supabase contient un mot de passe : `Read-Host` classique l'afficherait,
  et le passer en argument le laisserait dans l'historique du terminal ;
- `supabase.ps1` est refusé par la stratégie d'exécution PowerShell (« exécution
  de scripts est désactivée ») : il faut appeler `supabase.cmd` ;
- `supabase db dump` produit des fichiers de 0 octet si l'hôte est injoignable
  et n'affiche pas toujours d'erreur : d'où le contrôle systématique ;
- l'étape destructrice (`--appliquer`) exige de taper un mot en majuscules,
  afin qu'un appui involontaire sur Entrée ne puisse pas migrer la production.

Usage
-----
    cd backend
    .\\.venv\\Scripts\\python.exe -X utf8 _migrer_prod_supabase.py

Options
-------
    --dossier <chemin>   dossier de sauvegarde (défaut : Documents)
    --sans-sauvegarde    saute l'étape 1 (déconseillé, réservé aux cas où une
                         sauvegarde fraîche existe déjà)
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

BACKEND_DIR = Path(__file__).resolve().parent
SCRIPT_MIGRATION = BACKEND_DIR / "_migrate_school_id_pg.py"

# Schémas de la sauvegarde, dans l'ordre de lecture.
DUMP_SCHEMA = "01-schema.sql"
DUMP_DONNEES = "02-donnees.sql"
DUMP_ROLES = "03-roles.sql"

# Mot à taper pour déclencher réellement la migration (garde-fou).
MOT_CONFIRMATION = "MIGRER"

# Sous Windows, `supabase` est installé par npm sous trois formes : un script
# sans extension (shell), `supabase.cmd` (invocable) et `supabase.ps1`
# (bloqué par la stratégie d'exécution). On cherche donc explicitement le .cmd
# d'abord, puis on retombe sur le PATH.
EMPLACEMENTS_CLI = (
    Path(os.environ.get("APPDATA", "")) / "npm" / "supabase.cmd",
    Path(os.environ.get("ProgramFiles", "")) / "nodejs" / "supabase.cmd",
)


class Echec(RuntimeError):
    """Erreur contrôlée : on arrête le script proprement."""


def _titre(texte: str) -> None:
    print()
    print("=" * 74)
    print(texte)
    print("=" * 74)


def _etape(numero: int, total: int, texte: str) -> None:
    print()
    print(f"--- Étape {numero}/{total} : {texte} " + "-" * 20)


def trouver_cli() -> Path:
    """Localise un exécutable Supabase CLI utilisable."""
    for candidat in EMPLACEMENTS_CLI:
        if candidat and candidat.is_file():
            return candidat
    trouve = shutil.which("supabase.cmd") or shutil.which("supabase")
    if trouve:
        return Path(trouve)
    raise Echec(
        "Supabase CLI introuvable. Installez-la (npm i -g supabase) ou installez "
        "PostgreSQL pour utiliser pg_dump directement."
    )


def demander_url() -> str:
    """Chaîne de connexion : reprise de DATABASE_URL, sinon saisie masquée."""
    _titre("Chaîne de connexion PostgreSQL de production")

    # Si l'opérateur a déjà exporté DATABASE_URL dans son terminal, on la
    # reprend : cela évite une double saisie et permet d'automatiser le script.
    fournie = os.environ.get("DATABASE_URL", "").strip()
    if fournie:
        print("    DATABASE_URL est déjà défini dans cette session : reprise.")
        url = fournie
    else:
        print(
            "Dashboard Supabase > projet > bouton « Connect » > onglet\n"
            "« Session pooler » (port 5432), puis copiez la ligne complète :\n"
            "\n"
            "    postgresql://postgres.<ref>:<motdepasse>@<hote>:5432/postgres\n"
            "\n"
            "La saisie est masquée : rien ne s'affichera pendant le collage.\n"
            "Le mot de passe ne sera ni enregistré ni affiché sur le disque.\n"
        )
        try:
            url = getpass.getpass("URL de production (saisie masquée) : ").strip()
        except (KeyboardInterrupt, EOFError):
            raise Echec("Saisie interrompue.")
        if not url:
            raise Echec("Aucune URL saisie.")

    if not url.lower().startswith(("postgresql://", "postgres://")):
        raise Echec(f"Ce script ne migre que PostgreSQL (reçu : {url[:12]}...).")
    return url


def decrire_cible(url: str) -> str:
    """Résumé lisible SANS mot de passe, pour vérifier la cible."""
    parties = urlsplit(url)
    hote = parties.hostname or "?"
    port = f":{parties.port}" if parties.port else ""
    base = (parties.path or "/").lstrip("/") or "(défaut)"
    utilisateur = (parties.username or "?").split(":")[0]
    return f"{hote}{port}/{base}  —  utilisateur {utilisateur}"


def controler_url(url: str) -> None:
    """Avertit si le mot de passe ne semble pas encodé pour une URL."""
    if url.count("@") > 1:
        raise Echec(
            "L'URL contient plusieurs « @ ». Le mot de passe comporte "
            "probablement des caractères spéciaux non encodés : utilisez la "
            "ligne « Session pooler » copiée telle quelle depuis le dashboard, "
            "où le mot de passe est déjà encodé (par ex. @ devient %40)."
        )


def creer_dossier(racine: Path | None) -> Path:
    horodatage = datetime.now().strftime("%Y%m%d-%H%M%S")
    racine = racine or Path.home() / "Documents" / "sauvegardes-saint-collete"
    dossier = racine / horodatage
    dossier.mkdir(parents=True, exist_ok=True)
    return dossier


def lancer_dump(cli: Path, url: str, options: list[str], fichier: Path) -> None:
    commande = [str(cli), "db", "dump", "--db-url", url, *options, "-f", str(fichier)]
    # La commande elle-même n'est jamais affichée : elle contient l'URL.
    resultat = subprocess.run(
        commande,
        cwd=str(BACKEND_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "SUPABASE_TELEMETRY_DISABLED": "1"},
    )
    if resultat.returncode != 0:
        detail = (resultat.stderr or resultat.stdout or "").strip()
        raise Echec(
            f"Échec de la sauvegarde ({fichier.name}, code {resultat.returncode}).\n"
            f"        {detail[:400]}\n"
            "        Vérifiez que Docker Desktop est démarré et que l'hôte de "
            "la base est joignable."
        )


def compter_insertions(chemin: Path) -> dict[str, int]:
    """Compte les INSERT par table dans un dump de données."""
    motif = re.compile(r'INSERT INTO "public"\."([^"]+)"')
    comptes: dict[str, int] = {}
    with chemin.open(encoding="utf-8", errors="replace") as flux:
        for ligne in flux:
            trouve = motif.search(ligne)
            if trouve:
                comptes[trouve.group(1)] = comptes.get(trouve.group(1), 0) + 1
    return comptes


def sauvegarder(cli: Path, url: str, dossier: Path) -> None:
    """Écrit et contrôle la sauvegarde. Lève Echec si elle n'est pas fiable.

    Le schéma et les données sont indispensables : s'ils sont vides, on
    s'arrête. Les rôles, en revanche, sont purement documentaires : Supabase
    gère lui-même ses rôles et son dump peut être minuscule (un PostgreSQL
    local n'a que le rôle « postgres »). Un avertissement suffit donc.
    """
    dumps = (
        (DUMP_SCHEMA, [], "schéma", True),
        (DUMP_DONNEES, ["--data-only"], "données", True),
        (DUMP_ROLES, ["--role-only"], "rôles", False),
    )
    for nom, options, libelle, indispensable in dumps:
        fichier = dossier / nom
        print(f"    sauvegarde {libelle:8s} : {nom} ...", end=" ", flush=True)
        lancer_dump(cli, url, options, fichier)
        taille = fichier.stat().st_size if fichier.is_file() else 0
        print(f"{taille} octets", flush=True)
        if taille < 200:
            if indispensable:
                raise Echec(
                    f"La sauvegarde « {libelle} » est vide ou dérisoire "
                    f"({taille} octets). On s'arrête immédiatement : sans "
                    "sauvegarde fiable, aucune migration ne doit être tentée."
                )
            print("        (dump de rôles réduit : sans conséquence, il n'est "
                  "conservé que pour mémoire.)")

    # Contrôles de fond : le schéma doit décrire des tables et les données
    # doivent contenir des lignes.
    texte_schema = (dossier / DUMP_SCHEMA).read_text(encoding="utf-8", errors="replace")
    if "CREATE TABLE" not in texte_schema:
        raise Echec("Le dump de schéma ne contient aucune table : sauvegarde inexploitable.")

    insertions = compter_insertions(dossier / DUMP_DONNEES)
    total = sum(insertions.values())
    if total == 0:
        raise Echec("Le dump de données ne contient aucune ligne : sauvegarde inexploitable.")

    print()
    print(f"    Contrôles : {texte_schema.count('CREATE TABLE')} tables décrites, "
          f"{len(insertions)} tables peuplées, {total} instructions d'insertion.")
    print("    Détail par table :")
    for table in sorted(insertions):
        print(f"        {table:24s} {insertions[table]:6d}")
    print()
    print(f"    Sauvegarde dans : {dossier}")


def lancer_migration(url: str, appliquer: bool) -> int:
    """Exécute le script de migration (simulation ou application)."""
    commande = [sys.executable, "-X", "utf8", str(SCRIPT_MIGRATION)]
    if appliquer:
        commande.append("--appliquer")
    environnement = {**os.environ, "DATABASE_URL": url}
    # Sécurité : on ne veut jamais qu'un jeu de démonstration soit injecté dans
    # la base de production.
    environnement.pop("SEED_DEMO", None)
    resultat = subprocess.run(
        commande,
        cwd=str(BACKEND_DIR),
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environnement,
    )
    return resultat.returncode


def demander_confirmation() -> None:
    print()
    print("    Pour lancer la migration RÉELLE, tapez en majuscules : " + MOT_CONFIRMATION)
    print("    (tout autre réponse annule, sans rien modifier)")
    try:
        reponse = input("    Confirmation : ").strip()
    except (KeyboardInterrupt, EOFError):
        raise Echec("Confirmation interrompue : rien n'a été modifié.")
    if reponse != MOT_CONFIRMATION:
        raise Echec("Confirmation refusée : rien n'a été modifié.")


def main() -> int:
    analyseur = argparse.ArgumentParser(
        description="Migration guidée de la base PostgreSQL de production.")
    analyseur.add_argument("--dossier", type=Path, default=None,
                           help="dossier de sauvegarde (défaut : Documents)")
    analyseur.add_argument("--sans-sauvegarde", action="store_true",
                           help="saute la sauvegarde (déconseillé)")
    options = analyseur.parse_args()

    if not SCRIPT_MIGRATION.is_file():
        print(f"[ABANDON] {SCRIPT_MIGRATION.name} introuvable.")
        return 1

    _titre("Migration de la base de production — étapes guidées")

    url = demander_url()
    controler_url(url)

    print()
    print("    Cible détectée : " + decrire_cible(url))
    print()
    print("    Vérifiez que c'est bien le projet de l'établissement, puis validez.")
    try:
        if input("    Est-ce la bonne base ? (oui/non) : ").strip().lower() not in (
                "oui", "o", "yes", "y"):
            raise Echec("Cible refusée par l'opérateur.")
    except (KeyboardInterrupt, EOFError):
        raise Echec("Interrompu.")

    # 5 étapes avec sauvegarde (sauvegarde, simulation, confirmation,
    # migration, récapitulatif), 4 sans.
    total_etapes = 4 if options.sans_sauvegarde else 5
    numero = 0

    if options.sans_sauvegarde:
        print()
        print("    [!] Sauvegarde ignorée à la demande (--sans-sauvegarde).")
    else:
        numero += 1
        cli = trouver_cli()
        _etape(numero, total_etapes, "sauvegarde")
        dossier = creer_dossier(options.dossier)
        sauvegarder(cli, url, dossier)

    numero += 1
    _etape(numero, total_etapes, "simulation (aucune écriture)")
    code = lancer_migration(url, appliquer=False)
    if code != 0:
        raise Echec(
            "La simulation a échoué : la migration ne doit pas être tentée en "
            "l'état. Corrigez la cause indiquée ci-dessus."
        )
    print()
    print("    La simulation s'est déroulée sans erreur. Relisez la liste des")
    print("    instructions ci-dessus : aucun DROP ne doit viser une table hors")
    print("    du périmètre (contraintes uniquement), et le nombre de lignes")
    print("    annoncé doit correspondre à vos données réelles.")

    numero += 1
    _etape(numero, total_etapes, "confirmation")
    demander_confirmation()

    numero += 1
    _etape(numero, total_etapes, "migration réelle")
    code = lancer_migration(url, appliquer=True)
    if code != 0:
        raise Echec(
            "La migration a échoué. La transaction unique a annulé l'ensemble : "
            "la base est restée dans son état initial. Une sauvegarde est "
            "disponible si nécessaire."
        )

    numero += 1
    _etape(numero, total_etapes, "recapitulatif")
    print()
    print("    La base de production est migrée.")
    print()
    print("    À FAIRE MAINTENANT, sans attendre : déployer le nouveau code, car")
    print("    l'ancien schéma n'est plus celui de la base.")
    print()
    print("        Set-Location '" + str(BACKEND_DIR.parent) + "'")
    print("        vercel.cmd --prod --yes")
    print()
    print("    Puis vérifier le site : page d'accueil, connexion, tableau de bord.")
    print()
    print("    Effacez enfin la variable de la session :")
    print("        Remove-Item Env:DATABASE_URL, Env:SB_URL -ErrorAction SilentlyContinue")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Echec as erreur:
        print()
        print(f"[ABANDON] {erreur}")
        sys.exit(1)
    except KeyboardInterrupt:
        print()
        print("[ABANDON] Interrompu par l'opérateur.")
        sys.exit(130)
