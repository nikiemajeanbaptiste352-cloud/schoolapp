"""Phase 2 — capacités de l'interface servies par `GET /api/v1/etat`.

Le livrable de la Phase 2 est le **filtrage de l'interface** : le serveur
publie la liste des pages et des opérations d'écriture du rôle effectif, et
`js/ui.js` ne fait plus que l'appliquer. Avant, le menu et la garde des pages
décidaient seuls à partir de `sessionStorage` — une valeur modifiable à la
main — et **sans restriction par défaut** : toute page absente de la table
locale était visible par tout le monde.

Ce module vérifie :

1. la forme du contrat (`moi`, `capacites` = role / pages / operations /
   portee) et la non-régression des 9 clés historiques ;
2. le contenu réel par rôle (matrice de `app/services/perimetre.py`) ;
3. la **cohérence front/back** : les clés de pages et les opérations citées
   dans `js/ui.js`, `js/*.js` et `pages/*.html` existent bien côté serveur.
   C'est ce qui empêche une faute de frappe de désactiver silencieusement
   un garde-fou.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.auth import (
    ROLE_ADMIN,
    ROLE_ELEVE,
    ROLE_PARENT,
    ROLE_PROF,
    ROLE_SURVEILLANT,
)
from app.services.perimetre import (
    OPERATIONS_PAR_ROLE,
    PAGES_HORS_MENU,
    PAGES_MINIMALES,
    PAGES_PAR_ROLE,
    PORTEE_PERIMETRE,
    PORTEE_TOUS,
)
from tests.conftest import h
from tests.test_isolation_roles import (  # noqa: F401 — fixtures réutilisées
    eleve_token,
    parent_token,
    prof_token,
    surveillant_token,
)

RACINE = Path(__file__).resolve().parents[2]

#: Clés historiques de `/etat` : elles ne doivent jamais disparaître, le front
#: actuel les lit telles quelles.
CLES_HISTORIQUES = (
    "ecole",
    "classes",
    "matieres",
    "enseignants",
    "eleves",
    "notes",
    "presences",
    "paiements",
    "annonces",
)


def _etat(client, token: str) -> dict:
    resp = client.get("/api/v1/etat", headers=h(token))
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# 1. Forme du contrat
# ---------------------------------------------------------------------------
def test_etat_conserve_ses_cles_historiques_et_ajoute_les_capacites(client, admin_token):
    etat = _etat(client, admin_token)
    for cle in CLES_HISTORIQUES:
        assert cle in etat, f"clé historique manquante : {cle}"
    assert "moi" in etat and "capacites" in etat

    cap = etat["capacites"]
    assert set(cap) == {"role", "pages", "operations", "portee"}
    assert isinstance(cap["pages"], list) and isinstance(cap["operations"], list)
    assert etat["moi"]["role"] == cap["role"]
    assert etat["moi"]["nom"] and "@" in etat["moi"]["email"]


def test_moi_renvoie_le_role_effectif(client, admin_token):
    """Le rôle annoncé est celui du rattachement, pas une valeur du jeton."""
    etat = _etat(client, admin_token)
    assert etat["moi"]["role"] == ROLE_ADMIN


# ---------------------------------------------------------------------------
# 2. Contenu par rôle
# ---------------------------------------------------------------------------
def test_capacites_administrateur(client, admin_token):
    cap = _etat(client, admin_token)["capacites"]
    assert cap["role"] == ROLE_ADMIN
    assert cap["portee"] == PORTEE_TOUS
    assert {"utilisateurs", "paie", "teachers", "payments"} <= set(cap["pages"])
    # « Mon espace enseignant » (/mon-espace/*) est réservé au professeur par
    # `require_roles(ROLE_PROF)` : l'admin ne doit donc pas voir ces écrans.
    assert not {"mes-seances", "ma-paie"} & set(cap["pages"])
    assert {
        "eleves.ecrire",
        "membres.ecrire",
        "paie.ecrire",
        "notes.ecrire",
        "finance.ecrire",
    } <= set(cap["operations"])


def test_capacites_professeur(client, prof_token):
    cap = _etat(client, prof_token)["capacites"]
    assert cap["role"] == ROLE_PROF
    assert cap["portee"] == PORTEE_TOUS
    # Espace enseignant ouvert, administration et finance fermées.
    assert {"mes-seances", "ma-paie"} <= set(cap["pages"])
    assert not {"utilisateurs", "paie"} & set(cap["pages"])
    assert set(cap["operations"]) == {"notes.ecrire", "presences.ecrire", "seances.ecrire"}
    # Écritures de gestion interdites.
    assert not {"eleves.ecrire", "membres.ecrire", "finance.ecrire"} & set(cap["operations"])


def test_capacites_surveillant(client, surveillant_token):
    cap = _etat(client, surveillant_token)["capacites"]
    assert cap["role"] == ROLE_SURVEILLANT
    assert cap["portee"] == PORTEE_TOUS
    assert cap["operations"] == ["presences.ecrire"]
    # Vie scolaire : ni notes, ni bulletins, ni finance.
    assert not {"grades", "report-cards", "payments"} & set(cap["pages"])


def test_capacites_eleve(client, eleve_token):
    cap = _etat(client, eleve_token)["capacites"]
    assert cap["role"] == ROLE_ELEVE
    assert cap["portee"] == PORTEE_PERIMETRE
    assert cap["operations"] == []
    assert {"students", "grades", "report-cards", "payments"} <= set(cap["pages"])
    # Ni annuaire des enseignants, ni gestion des comptes, ni rémunérations.
    assert not {"teachers", "utilisateurs", "paie", "mes-seances", "ma-paie"} & set(
        cap["pages"]
    )


def test_capacites_parent(client, parent_token):
    """Cœur de la non-régression Phase 2 : un parent n'a aucun droit d'écriture."""
    cap = _etat(client, parent_token)["capacites"]
    assert cap["role"] == ROLE_PARENT
    assert cap["portee"] == PORTEE_PERIMETRE
    assert cap["operations"] == []
    assert {"students", "grades", "report-cards", "payments"} <= set(cap["pages"])
    assert not {"teachers", "utilisateurs", "paie"} & set(cap["pages"])


def test_tables_de_perimetre_stables():
    """Les listes du serveur sont la référence : on fige leur contenu exact.

    Toute modification doit être délibérée (elle change l'interface) et se
    répercuter dans `js/ui.js`, d'où l'égalité stricte vérifiée plus bas.
    """
    assert set(PAGES_PAR_ROLE) == {
        ROLE_ADMIN,
        ROLE_PROF,
        ROLE_SURVEILLANT,
        ROLE_ELEVE,
        ROLE_PARENT,
    }
    assert PAGES_MINIMALES == ("dashboard", "settings")
    assert PAGES_HORS_MENU == ("student-profile",)
    # Chaque rôle garde le tableau de bord et les paramètres.
    for role, pages in PAGES_PAR_ROLE.items():
        assert set(PAGES_MINIMALES) <= set(pages), f"{role} sans page minimale"
    # Aucune opération inventée : elle appartient à au moins un rôle.
    connues = {op for ops in OPERATIONS_PAR_ROLE.values() for op in ops}
    assert {"eleves.ecrire", "notes.ecrire", "presences.ecrire", "seances.ecrire"} <= connues
    # Les profils de consultation n'ont aucune écriture.
    assert OPERATIONS_PAR_ROLE[ROLE_ELEVE] == ()
    assert OPERATIONS_PAR_ROLE[ROLE_PARENT] == ()


# ---------------------------------------------------------------------------
# 3. Cohérence front / back
# ---------------------------------------------------------------------------
def _cles_ui_js() -> set[str]:
    """Clés de pages déclarées dans `js/ui.js` (table PAGES)."""
    source = (RACINE / "js" / "ui.js").read_text(encoding="utf-8")
    return set(re.findall(r'\{\s*key:\s*"([a-z-]+)"', source))


def test_chaque_page_du_menu_est_connue_du_serveur():
    """Une page ajoutée au front sans l'être côté serveur ne s'afficherait pas."""
    cles_front = _cles_ui_js()
    connues_serveur = set()
    for pages in PAGES_PAR_ROLE.values():
        connues_serveur |= set(pages)
    assert cles_front == connues_serveur, (
        f"front uniquement : {sorted(cles_front - connues_serveur)} | "
        f"serveur uniquement : {sorted(connues_serveur - cles_front)}"
    )


def test_operations_citees_dans_le_front_existent_cote_serveur():
    """`data-cap="x"` et `SM.peut("x")` doivent désigner une opération connue."""
    connues = {op for ops in OPERATIONS_PAR_ROLE.values() for op in ops}
    citees: set[str] = set()

    for fichier in (RACINE / "pages").glob("*.html"):
        citees |= set(re.findall(r'data-cap="([a-z]+\.[a-z]+)"', fichier.read_text(encoding="utf-8")))
    for fichier in (RACINE / "js").glob("*.js"):
        citees |= set(re.findall(r'peut\(\s*"([a-z]+\.[a-z]+)"\s*\)', fichier.read_text(encoding="utf-8")))

    assert citees, "aucune opération déclarée dans le front : le filtrage serait inerte"
    inconnues = citees - connues
    assert not inconnues, f"opérations inconnues du serveur : {sorted(inconnues)}"


def test_live_js_transmet_les_capacites_avant_ui_js():
    """Le passage de relais doit rester en place, sinon tout retombe en repli."""
    source = (RACINE / "js" / "live.js").read_text(encoding="utf-8")
    assert "window.SM_CAPACITES = etat.capacites" in source
    assert source.index("window.SM_CAPACITES") < source.index("chargerScripts(scripts)")


def test_ui_js_n_accepte_plus_une_page_inconnue():
    """La garde des pages doit rester fermée : refus par défaut."""
    source = (RACINE / "js" / "ui.js").read_text(encoding="utf-8")
    assert "function pageAutorisee" in source
    # Liste close : on n'autorise que ce qui est explicitement listé.
    assert 'if (liste.indexOf(cle) !== -1) return true;' in source
    # La fiche élève reste un écran hors menu, mais suit la page « students ».
    assert 'return liste.indexOf("students") !== -1;' in source
    # Aucun retour permissif en fin de fonction.
    fin = source.split("function pageAutorisee", 1)[1].split("}", 1)[0]
    assert "return false;" in fin


# ---------------------------------------------------------------------------
# 4. Spécificité des pages par rôle (Phase 2b)
# ---------------------------------------------------------------------------
ROLES_CONNUS = (ROLE_ADMIN, ROLE_PROF, ROLE_SURVEILLANT, ROLE_ELEVE, ROLE_PARENT)


def _textes_pages_ui_js() -> dict[str, set[str]]:
    """Table `TEXTES_PAGES` de `js/ui.js` : {page: {rôles cités}}."""
    source = (RACINE / "js" / "ui.js").read_text(encoding="utf-8")
    assert "var TEXTES_PAGES = {" in source, "table TEXTES_PAGES introuvable"
    bloc = source.split("var TEXTES_PAGES = {", 1)[1].split("\n  };", 1)[0]
    pages: dict[str, set[str]] = {}
    page: str | None = None
    for ligne in bloc.splitlines():
        m_page = re.match(r'^\s{4}"?([a-z-]+)"?:\s*\{\s*$', ligne)
        if m_page:
            page = m_page.group(1)
            pages[page] = set()
            continue
        m_role = re.match(r'^\s{6}"?([^":]+)"?:\s*"', ligne)
        if page and m_role:
            pages[page].add(m_role.group(1).strip())
    return pages


def _roles_autorises(page: str) -> set[str]:
    """Rôles ayant accès à la page (une page hors menu suit `students`)."""
    if page in PAGES_HORS_MENU:
        return {r for r, pages in PAGES_PAR_ROLE.items() if "students" in pages}
    return {r for r, pages in PAGES_PAR_ROLE.items() if page in pages}


def test_textes_pages_ne_cite_que_des_pages_et_des_roles_connus():
    """Une clé mal orthographiée laisserait la page sans texte adapté."""
    textes = _textes_pages_ui_js()
    assert textes, "aucune page décrite dans TEXTES_PAGES"

    connues = set(PAGES_HORS_MENU)
    for pages in PAGES_PAR_ROLE.values():
        connues |= set(pages)
    inconnues = set(textes) - connues
    assert not inconnues, f"pages inconnues du serveur : {sorted(inconnues)}"

    for page, cites in textes.items():
        mauvais = cites - set(ROLES_CONNUS)
        assert not mauvais, f"{page} : rôles inconnus {sorted(mauvais)}"


def test_chaque_page_parle_au_role_qui_l_ouvre():
    """Toute page décrite doit l'être pour chacun des rôles qui y accèdent :
    sinon le libellé générique d'un autre métier resterait affiché."""
    textes = _textes_pages_ui_js()
    manquants = []
    for role, pages in PAGES_PAR_ROLE.items():
        for page in pages:
            if page not in textes:
                continue  # page mono-rôle : le texte du HTML convient
            if role not in textes[page]:
                manquants.append(f"{page}/{role}")
    assert not manquants, f"pages sans texte spécifique : {sorted(manquants)}"


def test_aucun_texte_pour_un_role_sans_acces():
    """Réciproque : décrire une page pour un rôle qui n'y accède pas est un
    signe de décalage entre la matrice des pages et les libellés."""
    textes = _textes_pages_ui_js()
    intrus = []
    for page, cites in textes.items():
        for role in sorted(cites - _roles_autorises(page)):
            intrus.append(f"{page}/{role}")
    assert not intrus, f"textes prévus pour des rôles sans accès : {sorted(intrus)}"


# ---------------------------------------------------------------------------
# 5. Écran d'appel — « vie-scolaire »
# ---------------------------------------------------------------------------
def test_page_vie_scolaire_suit_l_operation_presences():
    """L'écran d'appel n'est ouvert qu'aux rôles qui détiennent l'opération.

    `presences.ecrire` était accordé sans qu'aucune page ne permette de s'en
    servir : l'écran doit exister exactement là où l'opération existe, ni plus
    (un profil qui ne peut pas écrire n'a rien à y faire) ni moins.
    """
    detenteurs = {r for r, ops in OPERATIONS_PAR_ROLE.items() if "presences.ecrire" in ops}
    porteurs = {r for r, pages in PAGES_PAR_ROLE.items() if "vie-scolaire" in pages}
    assert porteurs == detenteurs, (
        f"sans écran : {sorted(detenteurs - porteurs)} | "
        f"écran sans opération : {sorted(porteurs - detenteurs)}"
    )
    assert ROLE_SURVEILLANT in porteurs


def test_page_vie_scolaire_existe_et_est_cablee():
    """Fichiers présents, page déclarée, script chargé, écriture gardée."""
    html = (RACINE / "pages" / "vie-scolaire.html").read_text(encoding="utf-8")
    assert 'data-page="vie-scolaire"' in html
    assert 'data-auth="true"' in html
    assert 'data-page-js="vie-scolaire.js"' in html
    # La garde d'écriture porte sur l'opération exacte du serveur.
    assert 'data-cap="presences.ecrire"' in html

    script = (RACINE / "js" / "vie-scolaire.js").read_text(encoding="utf-8")
    assert 'SM.pageAutorisee("vie-scolaire"' in script
    assert "API.pointerPresence(" in script
    # Les trois statuts acceptés par `POST /api/v1/presences` (P|R|A).
    assert 'var LIB = { P: "Présent", R: "Retard", A: "Absent" }' in script
    assert 'var ORDRE = ["P", "R", "A"]' in script
    # Le payload doit porter les trois clés attendues par la route.
    assert "classe: classeSel" in script
    assert "date: jourSel" in script


def test_ecran_d_appel_accessible_aux_detenteurs(client, admin_token, prof_token, surveillant_token):
    """Le serveur publie la page aux trois rôles d'encadrement."""
    for token in (admin_token, prof_token, surveillant_token):
        cap = _etat(client, token)["capacites"]
        assert "vie-scolaire" in cap["pages"], f"{cap['role']} sans écran d'appel"
        assert "presences.ecrire" in cap["operations"], f"{cap['role']} sans droit de pointage"
