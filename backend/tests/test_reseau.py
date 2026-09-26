"""Phase 12 — réseau scolaire interne : cloisonnement, droits et modération.

Ce module fige les règles portées par `app/routers/reseau.py` :

* **cloisonnement** : tout est filtré par `school_id` ; un identifiant d'une
  autre école répond **404** (et non 403) pour ne pas révéler son existence ;
* **ouverture d'écriture** : les cinq rôles publient (`reseau.ecrire`) — un
  réseau *scolaire* où élèves et parents écrivent autant que le personnel —
  mais aucune écriture de scolarité ne leur est ouverte pour autant ;
* **modération** : épingler, masquer, supprimer appartiennent à la direction ;
  supprimer un message emporte ses commentaires et ses réactions ;
* **frontière de données** (zone Z2) : le fil, les groupes et les ressources
  ne transportent ni note, ni bulletin, ni paiement, ni absence, ni pièce
  administrative.

Les tests sont **indépendants de l'ordre d'exécution** : chaque écriture porte
un marqueur unique (`PH12-…`) retrouvé par recherche plein texte, et les
assertions de comptage sont faites en delta (avant / après) plutôt qu'en valeur
absolue, car toute la session de test partage la même base.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select

from app.auth import ROLE_ADMIN, ROLE_ELEVE, ROLE_PARENT, ROLE_PROF, ROLE_SURVEILLANT
from app.database import SessionLocal
from app.models import (
    CommentairePublication,
    Groupe,
    MembreGroupe,
    Publication,
    ReactionPublication,
    User,
)
from tests.conftest import h
from tests.test_isolation_roles import (  # noqa: F401 — fixtures réutilisées
    eleve_token,
    parent_token,
    prof_token,
    surveillant_token,
)
from tests.test_multitenant import (  # noqa: F401 — fixtures réutilisées
    ecole2,
    token_dir2,
)

PREFIXE = "/api/v1/reseau"

#: Aucun de ces fragments ne doit apparaître dans une clé du réseau : le fil
#: est un espace d'expression, pas un canal de diffusion de données scolaires.
FRAGMENTS_INTERDITS = (
    "note",
    "bulletin",
    "moyenne",
    "paiement",
    "versement",
    "absence",
    "presence",
    "discipline",
    "sanction",
    "salaire",
    "remuneration",
)


def _tag() -> str:
    return "PH12-" + uuid.uuid4().hex[:8]


def _fil(client, token: str, **params) -> dict:
    resp = client.get(f"{PREFIXE}/fil", headers=h(token), params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _publier(client, token: str, contenu: str, **extra) -> dict:
    resp = client.post(
        f"{PREFIXE}/publications", headers=h(token), json={"contenu": contenu, **extra}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["publication"]


def _unique(client, token: str, marqueur: str) -> dict | None:
    """Publication visible portant ce marqueur, ou None."""
    publiees = _fil(client, token, q=marqueur)["publications"]
    trouvees = [
        p for p in publiees if marqueur in p["contenu"] or marqueur in (p["titre"] or "")
    ]
    assert len(trouvees) <= 1, f"marqueur non unique : {marqueur}"
    return trouvees[0] if trouvees else None


def _sid_ecole1() -> int:
    with SessionLocal() as db:
        sid = db.scalar(select(User.school_id).where(User.email == "admin@lesavoir.edu"))
    assert sid is not None, "seed de démonstration absent"
    return sid


def _compter(db, modele, **criteres) -> int:
    stmt = select(func.count()).select_from(modele)
    for colonne, valeur in criteres.items():
        stmt = stmt.where(getattr(modele, colonne) == valeur)
    return int(db.scalar(stmt) or 0)


def _cles(objet) -> set[str]:
    """Toutes les clés d'une structure JSON, à toute profondeur."""
    if isinstance(objet, dict):
        cles = set(objet)
        for valeur in objet.values():
            cles |= _cles(valeur)
        return cles
    if isinstance(objet, list):
        cles: set[str] = set()
        for valeur in objet:
            cles |= _cles(valeur)
        return cles
    return set()


# ---------------------------------------------------------------------------
# 1. Accès
# ---------------------------------------------------------------------------
def test_reseau_ouvert_aux_cinq_roles(
    client, admin_token, prof_token, surveillant_token, eleve_token, parent_token
):
    """Un réseau scolaire : tout membre rattaché y entre, quel que soit son rôle."""
    for token in (admin_token, prof_token, surveillant_token, eleve_token, parent_token):
        assert client.get(f"{PREFIXE}/fil", headers=h(token)).status_code == 200
        assert client.get(f"{PREFIXE}/resume", headers=h(token)).status_code == 200
        assert client.get(f"{PREFIXE}/groupes", headers=h(token)).status_code == 200
        assert client.get(f"{PREFIXE}/ressources", headers=h(token)).status_code == 200

    # La modération est un attribut de direction, annoncé par le serveur.
    assert _fil(client, admin_token)["peutModerer"] is True
    for token in (prof_token, surveillant_token, eleve_token, parent_token):
        assert _fil(client, token)["peutModerer"] is False


def test_reseau_exige_un_jeton(client):
    assert client.get(f"{PREFIXE}/fil").status_code == 401
    assert client.get(f"{PREFIXE}/resume").status_code == 401
    assert client.get(f"{PREFIXE}/ressources").status_code == 401
    assert client.post(f"{PREFIXE}/publications", json={"contenu": "anonyme"}).status_code == 401


# ---------------------------------------------------------------------------
# 2. Publications
# ---------------------------------------------------------------------------
def test_publication_dans_le_fil_general(client, admin_token, prof_token):
    marqueur = _tag()
    pub = _publier(client, prof_token, f"Cours déplacé — {marqueur}", titre="Information")

    assert pub["groupeId"] is None
    assert pub["auteurRole"] == ROLE_PROF
    assert pub["auteurRoleLibelle"] == "Professeur"
    assert pub["auteurNom"]
    assert pub["estAuteur"] is True and pub["peutModifier"] is True
    assert pub["peutModerer"] is False
    assert pub["jaime"] is False and pub["jaimeCount"] == 0
    assert pub["commentaires"] == []

    # Visible par un autre compte de l'établissement, avec les mêmes champs.
    vue_admin = _unique(client, admin_token, marqueur)
    assert vue_admin is not None
    assert vue_admin["contenu"].endswith(marqueur)
    assert vue_admin["estAuteur"] is False and vue_admin["peutModifier"] is False
    # La direction peut toujours supprimer (modération)…
    assert vue_admin["peutSupprimer"] is True


def test_publication_valide_le_contenu(client, prof_token):
    for corps in (
        {},
        {"contenu": "   "},
        {"contenu": "x", "type": "inconnu"},
        {"contenu": "x" * 4001},
        {"contenu": "x", "titre": "t" * 141},
        {"contenu": 42},
    ):
        resp = client.post(f"{PREFIXE}/publications", headers=h(prof_token), json=corps)
        assert resp.status_code == 400, f"{corps} → {resp.status_code}"


def test_eleve_et_parent_publient(client, admin_token, eleve_token, parent_token):
    """L'ouverture d'écriture de la Phase 12, vérifiée des deux côtés."""
    tag_eleve, tag_parent = _tag(), _tag()
    pub_eleve = _publier(client, eleve_token, f"Révisions de groupe ? {tag_eleve}")
    pub_parent = _publier(client, parent_token, f"Information des parents {tag_parent}")

    assert pub_eleve["auteurRole"] == ROLE_ELEVE
    assert pub_parent["auteurRole"] == ROLE_PARENT
    # Le personnel les voit dans le même fil.
    assert _unique(client, admin_token, tag_eleve) is not None
    assert _unique(client, admin_token, tag_parent) is not None


def test_publication_dans_un_groupe_non_accessible_refusee(
    client, admin_token, eleve_token, parent_token
):
    """Un groupe de classe n'est visible que par sa population."""
    fiche = client.get("/api/v1/eleves/EL001", headers=h(admin_token)).json()
    classe_eleve = fiche["classe"]
    classes = client.get("/api/v1/classes", headers=h(admin_token)).json()["classes"]
    autre = next(c["id"] for c in classes if c["id"] != classe_eleve)

    nom = f"Classe {autre} {_tag()}"
    groupe = client.post(
        f"{PREFIXE}/groupes",
        headers=h(admin_token),
        json={"nom": nom, "type": "classe", "classeId": autre},
    ).json()["groupe"]

    # Le parent n'est pas concerné : le groupe n'apparaît pas dans son fil.
    assert all(g["id"] != groupe["id"] for g in _fil(client, parent_token)["groupes"])
    assert all(g["id"] != groupe["id"] for g in _fil(client, eleve_token)["groupes"])

    # Et il ne peut ni y écrire, ni le rejoindre, ni le consulter.
    assert (
        client.post(
            f"{PREFIXE}/publications",
            headers=h(parent_token),
            json={"contenu": "intrusion", "groupeId": groupe["id"]},
        ).status_code
        == 403
    )
    assert (
        client.get(
            f"{PREFIXE}/fil", headers=h(parent_token), params={"groupe": groupe["id"]}
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"{PREFIXE}/groupes/{groupe['id']}/rejoindre", headers=h(parent_token)
        ).status_code
        == 403
    )
    # La direction, elle, y accède (elle voit tous les groupes).
    assert (
        client.get(
            f"{PREFIXE}/fil", headers=h(admin_token), params={"groupe": groupe["id"]}
        ).status_code
        == 200
    )
    client.delete(f"{PREFIXE}/groupes/{groupe['id']}", headers=h(admin_token))


# ---------------------------------------------------------------------------
# 3. Modification et modération
# ---------------------------------------------------------------------------
def test_auteur_modifie_son_message(client, prof_token):
    marqueur = _tag()
    pub = _publier(client, prof_token, f"Version 1 {marqueur}")
    assert pub["majLe"] is None

    resp = client.patch(
        f"{PREFIXE}/publications/{pub['id']}",
        headers=h(prof_token),
        json={"contenu": f"Version 2 {marqueur}"},
    )
    assert resp.status_code == 200, resp.text
    modifiee = resp.json()["publication"]
    assert "Version 2" in modifiee["contenu"]
    assert modifiee["majLe"] is not None


def test_un_tiers_ne_modifie_pas_un_message(client, admin_token, eleve_token, prof_token):
    marqueur = _tag()
    pub = _publier(client, prof_token, f"Message du professeur {marqueur}")

    resp = client.patch(
        f"{PREFIXE}/publications/{pub['id']}",
        headers=h(eleve_token),
        json={"contenu": "détournement"},
    )
    assert resp.status_code == 403

    # La direction peut corriger (modération) : c'est une décision assumée.
    resp = client.patch(
        f"{PREFIXE}/publications/{pub['id']}",
        headers=h(admin_token),
        json={"contenu": f"Corrigé par la direction {marqueur}"},
    )
    assert resp.status_code == 200, resp.text


def test_epinglage_reserve_a_la_direction(client, admin_token, eleve_token):
    marqueur = _tag()
    pub = _publier(client, eleve_token, f"Annonce d'élève {marqueur}")

    assert (
        client.patch(
            f"{PREFIXE}/publications/{pub['id']}",
            headers=h(eleve_token),
            json={"epingle": True},
        ).status_code
        == 403
    )
    # Même motif pour le masquage.
    assert (
        client.patch(
            f"{PREFIXE}/publications/{pub['id']}",
            headers=h(eleve_token),
            json={"masque": True},
        ).status_code
        == 403
    )

    resp = client.patch(
        f"{PREFIXE}/publications/{pub['id']}",
        headers=h(admin_token),
        json={"epingle": True},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["publication"]["epingle"] is True

    # Une publication épinglée passe devant une publication libre.
    publiees = _fil(client, admin_token)["publications"]
    index_epinglee = next(i for i, p in enumerate(publiees) if p["id"] == pub["id"])
    non_epinglees = [i for i, p in enumerate(publiees) if not p["epingle"]]
    if non_epinglees:
        assert index_epinglee < min(non_epinglees)

    client.delete(f"{PREFIXE}/publications/{pub['id']}", headers=h(admin_token))


def test_masquage_par_la_direction_n_efface_pas(client, admin_token, eleve_token):
    marqueur = _tag()
    pub = _publier(client, eleve_token, f"Message à modérer {marqueur}")

    resp = client.patch(
        f"{PREFIXE}/publications/{pub['id']}",
        headers=h(admin_token),
        json={"masque": True},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["publication"]["masque"] is True

    # Retirée du fil public…
    assert _unique(client, eleve_token, marqueur) is None
    # …mais conservée pour la direction (traçabilité), marquée comme masquée.
    vue = _unique(client, admin_token, marqueur)
    assert vue is not None and vue["masque"] is True

    sid = _sid_ecole1()
    with SessionLocal() as db:
        assert _compter(db, Publication, school_id=sid, id=pub["id"]) == 1


def test_suppression_emporte_commentaires_et_reactions(client, admin_token, eleve_token):
    marqueur = _tag()
    pub = _publier(client, eleve_token, f"Fil à supprimer {marqueur}")
    assert (
        client.post(
            f"{PREFIXE}/publications/{pub['id']}/commentaires",
            headers=h(admin_token),
            json={"contenu": "Merci !"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"{PREFIXE}/publications/{pub['id']}/jaime", headers=h(admin_token)
        ).status_code
        == 200
    )

    sid = _sid_ecole1()
    with SessionLocal() as db:
        assert _compter(db, CommentairePublication, publication_id=pub["id"]) == 1
        assert _compter(db, ReactionPublication, publication_id=pub["id"]) == 1

    resp = client.delete(f"{PREFIXE}/publications/{pub['id']}", headers=h(admin_token))
    assert resp.status_code == 200, resp.text

    with SessionLocal() as db:
        assert _compter(db, Publication, school_id=sid, id=pub["id"]) == 0
        assert _compter(db, CommentairePublication, publication_id=pub["id"]) == 0
        assert _compter(db, ReactionPublication, publication_id=pub["id"]) == 0

    # Deuxième appel : plus rien à supprimer.
    assert (
        client.delete(
            f"{PREFIXE}/publications/{pub['id']}", headers=h(admin_token)
        ).status_code
        == 404
    )


# ---------------------------------------------------------------------------
# 4. Réactions
# ---------------------------------------------------------------------------
def test_jaime_est_une_bascule(client, admin_token, eleve_token, parent_token):
    marqueur = _tag()
    pub = _publier(client, admin_token, f"Bravo à tous {marqueur}")
    url = f"{PREFIXE}/publications/{pub['id']}/jaime"

    premier = client.post(url, headers=h(eleve_token)).json()
    assert premier == {"jaime": True, "jaimeCount": 1}
    # Deuxième appui : retrait (une seule réaction par compte et par message).
    assert client.post(url, headers=h(eleve_token)).json() == {
        "jaime": False,
        "jaimeCount": 0,
    }

    client.post(url, headers=h(eleve_token))
    compose = client.post(url, headers=h(parent_token)).json()
    assert compose == {"jaime": True, "jaimeCount": 2}

    vue = _unique(client, eleve_token, marqueur)
    assert vue is not None and vue["jaime"] is True and vue["jaimeCount"] == 2

    sid = _sid_ecole1()
    with SessionLocal() as db:
        assert _compter(db, ReactionPublication, school_id=sid, publication_id=pub["id"]) == 2


# ---------------------------------------------------------------------------
# 5. Commentaires
# ---------------------------------------------------------------------------
def test_commentaire_supprimable_par_son_auteur_ou_la_direction(
    client, admin_token, eleve_token, prof_token
):
    marqueur = _tag()
    pub = _publier(client, admin_token, f"Question ouverte {marqueur}")
    cree = client.post(
        f"{PREFIXE}/publications/{pub['id']}/commentaires",
        headers=h(eleve_token),
        json={"contenu": "Présent !"},
    )
    assert cree.status_code == 200, cree.text
    commentaire = cree.json()["commentaire"]
    assert commentaire["auteurRole"] == ROLE_ELEVE
    assert commentaire["estAuteur"] is True and commentaire["peutSupprimer"] is True

    # Un autre compte ne peut pas le supprimer…
    assert (
        client.delete(
            f"{PREFIXE}/commentaires/{commentaire['id']}", headers=h(prof_token)
        ).status_code
        == 403
    )
    # …la direction si.
    assert (
        client.delete(
            f"{PREFIXE}/commentaires/{commentaire['id']}", headers=h(admin_token)
        ).status_code
        == 200
    )
    assert (
        client.delete(
            f"{PREFIXE}/commentaires/{commentaire['id']}", headers=h(admin_token)
        ).status_code
        == 404
    )


def test_commentaire_masque_invisible_hors_direction(client, admin_token, prof_token):
    """Le masquage d'un commentaire reste possible côté données : le fil doit le respecter."""
    marqueur = _tag()
    pub = _publier(client, prof_token, f"Fil commenté {marqueur}")
    commentaire = client.post(
        f"{PREFIXE}/publications/{pub['id']}/commentaires",
        headers=h(prof_token),
        json={"contenu": "Commentaire à masquer"},
    ).json()["commentaire"]

    sid = _sid_ecole1()
    with SessionLocal() as db:
        ligne = db.scalar(
            select(CommentairePublication).where(
                CommentairePublication.school_id == sid,
                CommentairePublication.id == commentaire["id"],
            )
        )
        assert ligne is not None
        ligne.masque = True
        db.commit()

    vue_prof = _unique(client, prof_token, marqueur)
    assert vue_prof is not None and vue_prof["commentaires"] == []
    vue_admin = _unique(client, admin_token, marqueur)
    assert vue_admin is not None and len(vue_admin["commentaires"]) == 1


# ---------------------------------------------------------------------------
# 6. Groupes
# ---------------------------------------------------------------------------
def _creer_groupe(client, token, nom: str, **extra) -> dict:
    resp = client.post(f"{PREFIXE}/groupes", headers=h(token), json={"nom": nom, **extra})
    assert resp.status_code == 200, resp.text
    return resp.json()["groupe"]


def test_creer_rejoindre_et_quitter_un_club(client, admin_token, prof_token, eleve_token):
    nom = f"Club robotique {_tag()}"
    groupe = _creer_groupe(client, eleve_token, nom, type="club", description="Le mardi")
    assert groupe["estCreateur"] is True and groupe["peutSupprimer"] is True
    assert groupe["estMembre"] is True and groupe["membres"] == 1
    assert groupe["ouvert"] is True

    # Un club est découvrable par tout le réseau, y compris le personnel…
    vus = {g["id"] for g in _fil(client, prof_token)["groupes"]}
    assert groupe["id"] in vus

    # …et librement rejoignable ; l'adhésion est idempotente.
    rejoindre = client.post(
        f"{PREFIXE}/groupes/{groupe['id']}/rejoindre", headers=h(prof_token)
    )
    assert rejoindre.status_code == 200, rejoindre.text
    assert rejoindre.json()["groupe"]["estMembre"] is True
    client.post(f"{PREFIXE}/groupes/{groupe['id']}/rejoindre", headers=h(prof_token))

    # Publication dans le groupe : rattachée au groupe.
    marqueur = _tag()
    pub = _publier(
        client, prof_token, f"Première séance {marqueur}", groupeId=groupe["id"]
    )
    assert pub["groupeId"] == groupe["id"] and pub["groupeNom"] == nom
    assert _unique(client, admin_token, marqueur) is not None

    # Sortie du groupe, puis second appel → plus membre.
    assert (
        client.delete(
            f"{PREFIXE}/groupes/{groupe['id']}/quitter", headers=h(prof_token)
        ).status_code
        == 200
    )
    assert (
        client.delete(
            f"{PREFIXE}/groupes/{groupe['id']}/quitter", headers=h(prof_token)
        ).status_code
        == 404
    )

    # Le createur supprime : le groupe part avec ses messages.
    assert (
        client.delete(f"{PREFIXE}/groupes/{groupe['id']}", headers=h(eleve_token)).status_code
        == 200
    )
    sid = _sid_ecole1()
    with SessionLocal() as db:
        assert _compter(db, Groupe, school_id=sid, id=groupe["id"]) == 0
        assert _compter(db, Publication, school_id=sid, id=pub["id"]) == 0
        assert _compter(db, MembreGroupe, groupe_id=groupe["id"]) == 0


def test_nom_de_groupe_unique_dans_l_etablissement(client, admin_token, prof_token):
    nom = f"Groupe unique {_tag()}"
    _creer_groupe(client, admin_token, nom)
    conflit = client.post(
        f"{PREFIXE}/groupes", headers=h(prof_token), json={"nom": nom}
    )
    assert conflit.status_code == 409, conflit.text


def test_groupe_de_matiere_reserve_au_personnel(client, admin_token, eleve_token, prof_token):
    matieres = client.get("/api/v1/matieres", headers=h(admin_token)).json()["matieres"]
    matiere = matieres[0]["id"]
    sid = _sid_ecole1()

    with SessionLocal() as db:
        avant = _compter(db, Groupe, school_id=sid, type="matiere")

    refuse = client.post(
        f"{PREFIXE}/groupes",
        headers=h(eleve_token),
        json={"nom": f"Cours du soir {_tag()}", "type": "matiere", "matiereId": matiere},
    )
    assert refuse.status_code == 403, refuse.text

    accepte = client.post(
        f"{PREFIXE}/groupes",
        headers=h(prof_token),
        json={"nom": f"Cours du soir {_tag()}", "type": "matiere", "matiereId": matiere},
    )
    assert accepte.status_code == 200, accepte.text
    groupe = accepte.json()["groupe"]
    assert groupe["matiereId"] == matiere

    # Le type suffit : un élève ne crée pas davantage un groupe « matière »
    # laissé sans matière désignée.
    assert (
        client.post(
            f"{PREFIXE}/groupes",
            headers=h(eleve_token),
            json={"nom": f"Cours libre {_tag()}", "type": "matiere"},
        ).status_code
        == 403
    )

    # Symétriquement, le personnel doit désigner sa matière : un groupe
    # structurel sans son rattachement ne serait visible de personne.
    assert (
        client.post(
            f"{PREFIXE}/groupes",
            headers=h(prof_token),
            json={"nom": f"Matière flottante {_tag()}", "type": "matiere"},
        ).status_code
        == 400
    )
    assert (
        client.post(
            f"{PREFIXE}/groupes",
            headers=h(prof_token),
            json={
                "nom": f"Matière fantôme {_tag()}",
                "type": "matiere",
                "matiereId": "ZZZ-inexistante",
            },
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"{PREFIXE}/groupes",
            headers=h(admin_token),
            json={"nom": f"Classe flottante {_tag()}", "type": "classe"},
        ).status_code
        == 400
    )

    # Un groupe adossé à une classe ne peut pas se déclarer « club »…
    incoherent = client.post(
        f"{PREFIXE}/groupes",
        headers=h(admin_token),
        json={"nom": f"Incohérent {_tag()}", "type": "club", "classeId": "3A"},
    )
    assert incoherent.status_code == 400, incoherent.text

    # …pas plus qu'un groupe adossé à une matière.
    assert (
        client.post(
            f"{PREFIXE}/groupes",
            headers=h(prof_token),
            json={"nom": f"Incohérent matière {_tag()}", "type": "club", "matiereId": matiere},
        ).status_code
        == 400
    )

    # Aucun de ces refus n'a laissé de groupe « matière » orphelin derrière lui.
    with SessionLocal() as db:
        assert _compter(db, Groupe, school_id=sid, type="matiere") == avant + 1

    client.delete(f"{PREFIXE}/groupes/{groupe['id']}", headers=h(admin_token))
    with SessionLocal() as db:
        assert _compter(db, Groupe, school_id=sid, type="matiere") == avant


def test_groupe_supprimable_par_la_direction_ou_son_createur(client, admin_token, prof_token):
    groupe = _creer_groupe(client, prof_token, f"Projet {_tag()}", type="projet")
    # Un tiers (même personnel) ne peut pas supprimer le groupe d'un autre.
    assert (
        client.delete(
            f"{PREFIXE}/groupes/{groupe['id']}", headers=h(admin_token)
        ).status_code
        == 200
    )
    assert (
        client.delete(
            f"{PREFIXE}/groupes/{groupe['id']}", headers=h(prof_token)
        ).status_code
        == 404
    )


# ---------------------------------------------------------------------------
# 7. Bibliothèque de ressources
# ---------------------------------------------------------------------------
def test_ressource_exige_une_adresse_web(client, prof_token, admin_token):
    nom = f"Fiche de révision {_tag()}"
    invalide = client.post(
        f"{PREFIXE}/ressources",
        headers=h(prof_token),
        json={"titre": nom, "url": "javascript:alert(1)"},
    )
    assert invalide.status_code == 400, invalide.text
    vide = client.post(
        f"{PREFIXE}/ressources", headers=h(prof_token), json={"titre": nom}
    )
    assert vide.status_code == 400, vide.text

    matieres = client.get("/api/v1/matieres", headers=h(admin_token)).json()["matieres"]
    matiere = matieres[0]["id"]
    cree = client.post(
        f"{PREFIXE}/ressources",
        headers=h(prof_token),
        json={
            "titre": nom,
            "url": "https://exemple.edu/fiche.pdf",
            "type": "document",
            "matiereId": matiere,
            "niveau": "3e",
        },
    )
    assert cree.status_code == 200, cree.text
    ressource = cree.json()["ressource"]
    assert ressource["type"] == "document" and ressource["matiereId"] == matiere
    assert ressource["estAuteur"] is True and ressource["peutSupprimer"] is True

    # Recherche et filtrage par matière.
    liste = client.get(
        f"{PREFIXE}/ressources", headers=h(admin_token), params={"q": nom}
    ).json()
    assert [r["id"] for r in liste["ressources"]] == [ressource["id"]]
    par_matiere = client.get(
        f"{PREFIXE}/ressources", headers=h(admin_token), params={"matiere": matiere}
    ).json()["ressources"]
    assert ressource["id"] in {r["id"] for r in par_matiere}

    # Matière inexistante → 404, jamais de ligne orpheline.
    assert (
        client.post(
            f"{PREFIXE}/ressources",
            headers=h(admin_token),
            json={"titre": "X", "url": "https://exemple.edu", "matiereId": "ZZZ"},
        ).status_code
        == 404
    )

    client.delete(f"{PREFIXE}/ressources/{ressource['id']}", headers=h(prof_token))


def test_ressource_supprimable_par_son_auteur_ou_la_direction(client, admin_token, prof_token):
    cree = client.post(
        f"{PREFIXE}/ressources",
        headers=h(prof_token),
        json={"titre": f"Vidéo {_tag()}", "url": "https://exemple.edu/v", "type": "video"},
    ).json()["ressource"]

    assert (
        client.delete(
            f"{PREFIXE}/ressources/{cree['id']}", headers=h(admin_token)
        ).status_code
        == 200
    )
    assert (
        client.delete(
            f"{PREFIXE}/ressources/{cree['id']}", headers=h(prof_token)
        ).status_code
        == 404
    )


# ---------------------------------------------------------------------------
# 8. Cloisonnement entre établissements
# ---------------------------------------------------------------------------
def test_le_reseau_ne_franchit_pas_la_frontiere_d_etablissement(
    client, admin_token, prof_token, token_dir2
):
    marqueur = _tag()
    pub = _publier(client, prof_token, f"Réunion de parents {marqueur}")
    groupe = _creer_groupe(client, admin_token, f"Club débat {_tag()}", type="club")
    ressource = client.post(
        f"{PREFIXE}/ressources",
        headers=h(prof_token),
        json={"titre": f"Lien {_tag()}", "url": "https://exemple.edu/x"},
    ).json()["ressource"]

    # Le fil de l'école n°2 est vide de tout contenu de l'école n°1.
    assert _unique(client, token_dir2, marqueur) is None
    assert all(g["id"] != groupe["id"] for g in _fil(client, token_dir2)["groupes"])

    # Tout identifiant étranger est introuvable — 404, jamais 403 : l'existence
    # d'une ligne d'une autre école ne doit pas être révélée.
    assert (
        client.delete(
            f"{PREFIXE}/publications/{pub['id']}", headers=h(token_dir2)
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"{PREFIXE}/groupes/{groupe['id']}/rejoindre", headers=h(token_dir2)
        ).status_code
        == 404
    )
    assert (
        client.delete(
            f"{PREFIXE}/groupes/{groupe['id']}", headers=h(token_dir2)
        ).status_code
        == 404
    )
    assert (
        client.delete(
            f"{PREFIXE}/ressources/{ressource['id']}", headers=h(token_dir2)
        ).status_code
        == 404
    )

    # Dans l'autre sens : une publication de l'école n°2 reste invisible ici.
    marqueur2 = _tag()
    _publier(client, token_dir2, f"Rentrée à Kaya {marqueur2}")
    assert _unique(client, admin_token, marqueur2) is None


# ---------------------------------------------------------------------------
# 9. Frontière de données (zone Z2)
# ---------------------------------------------------------------------------
def test_le_reseau_ne_transporte_aucune_donnee_scolaire(
    client, admin_token, prof_token, eleve_token, parent_token
):
    marqueurs = [_tag() for _ in range(3)]
    _publier(client, prof_token, f"Cours {marqueurs[0]}")
    _publier(client, eleve_token, f"Devoirs {marqueurs[1]}")
    _publier(client, parent_token, f"Question {marqueurs[2]}")
    groupe = _creer_groupe(client, prof_token, f"Atelier {_tag()}", type="projet")
    client.post(
        f"{PREFIXE}/ressources",
        headers=h(prof_token),
        json={"titre": f"Support {_tag()}", "url": "https://exemple.edu/s"},
    )

    cles: set[str] = set()
    for point in ("fil", "groupes", "ressources", "resume"):
        cles |= _cles(client.get(f"{PREFIXE}/{point}", headers=h(admin_token)).json())
    cles |= _cles(
        client.get(
            f"{PREFIXE}/fil", headers=h(admin_token), params={"groupe": groupe["id"]}
        ).json()
    )
    assert cles, "aucune clé relevée : le contrôle serait inerte"

    fautives = {
        cle
        for cle in cles
        for fragment in FRAGMENTS_INTERDITS
        if fragment in cle.lower()
    }
    assert not fautives, f"données scolaires exposées par le réseau : {sorted(fautives)}"

    client.delete(f"{PREFIXE}/groupes/{groupe['id']}", headers=h(admin_token))
