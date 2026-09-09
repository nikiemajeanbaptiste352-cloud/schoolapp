"""Espace enseignant : cahier de présence numérisé et rémunération.

Couvre le parcours approuvé : l'enseignant signe des séances réellement
données (une entrée par date / classe / heure de début), la direction fixe
le taux horaire puis génère et paie les fiches. Les heures versées sont
celles réellement signées (rémunération à la vacation), signature horodatée.
"""

from datetime import date

from tests.conftest import auth, h

PROF = "j.ouedraogo@lesavoir.edu"  # fiche T001 — S1, classes 3A & 3B
PROF2 = "s.kabore@lesavoir.edu"    # fiche T002 — autre enseignant
ADMIN = "admin@lesavoir.edu"


def _ajd() -> str:
    return date.today().isoformat()


def _mois_courant() -> str:
    return date.today().strftime("%Y-%m")


def _signer(client, token, **sur):
    corps = {
        "date": _ajd(),
        "classe_id": "3A",
        "matiere_id": "S1",
        "heure_debut": "08:00",
        "heure_fin": "10:00",
    }
    corps.update(sur)
    return client.post("/api/v1/mon-espace/seances", headers=h(token), json=corps)


def test_profil_espace_lie_a_la_fiche_enseignant(client):
    t = auth(client, PROF)
    r = client.get("/api/v1/mon-espace/profil", headers=h(t))
    assert r.status_code == 200, r.text
    ens = r.json()["enseignant"]
    assert ens["id"] == "T001"
    assert ens["matiereId"] == "S1"
    assert {c["id"] for c in ens["classes"]} == {"3A", "3B"}
    data = r.json()
    assert data["tauxHoraire"] == 0
    assert data["mois"] == _mois_courant()


def test_signature_seance_horodatee(client):
    t = auth(client, PROF)
    r = _signer(client, t)
    assert r.status_code == 201, r.text
    s = r.json()
    assert s["classeId"] == "3A"
    assert s["classeNom"]  # nom d'affichage (ex. "3e A")
    assert s["matiereId"] == "S1"
    assert s["heures"] == 2.0
    assert s["creeLe"]  # signature horodatée
    assert s["enseignantNom"].lower().startswith("ouedraogo") or s["enseignantNom"]


def test_doublon_signature_refuse(client):
    t = auth(client, PROF)
    r = _signer(client, t)  # même date, même classe, même début
    assert r.status_code == 409
    assert "déjà signée" in r.json()["detail"]


def test_classe_non_affectee_refusee(client):
    t = auth(client, PROF)
    r = _signer(client, t, classe_id="4A")
    assert r.status_code == 400
    assert "classe" in r.json()["detail"]


def test_matiere_non_liee_a_fiche_refusee(client):
    t = auth(client, PROF)
    r = _signer(client, t, matiere_id="S2")
    assert r.status_code == 400


def test_horaires_inverses_refuses(client):
    t = auth(client, PROF)
    r = _signer(client, t, heure_debut="10:00", heure_fin="08:00")
    assert r.status_code == 400


def test_date_future_refusee(client):
    t = auth(client, PROF)
    r = _signer(client, t, date="2999-01-01")
    assert r.status_code == 400
    assert "futur" in r.json()["detail"]


def test_historique_du_mois_enseignant(client):
    t = auth(client, PROF)
    r = client.get(
        f"/api/v1/mon-espace/seances?mois={_mois_courant()}", headers=h(t)
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["nbSeances"] == 1
    assert data["heuresTotal"] == 2.0
    assert data["seances"][0]["date"] == _ajd()


def test_enseignant_ne_supprime_pas_la_seance_d_un_autre(client):
    autres = auth(client, PROF2)
    t1 = auth(client, PROF)
    liste = client.get(
        f"/api/v1/mon-espace/seances?mois={_mois_courant()}", headers=h(t1)
    ).json()
    sid = liste["seances"][0]["id"]
    r = client.delete(f"/api/v1/mon-espace/seances/{sid}", headers=h(autres))
    assert r.status_code == 403


def test_professeur_sans_fiche_refuse(client, admin_token):
    # Compte Professeur dont l'email ne correspond à aucune fiche enseignant
    cree = client.post(
        "/api/v1/auth/comptes",
        headers=h(admin_token),
        json={
            "nom": "Sans Fiche",
            "email": "sans.fiche@exemple.edu",
            "password": "Savoir2026!",
            "role": "Professeur",
        },
    )
    assert cree.status_code == 201, cree.text
    assert cree.json()["enseignant_id"] is None
    t = auth(client, "sans.fiche@exemple.edu")
    r = client.get("/api/v1/mon-espace/profil", headers=h(t))
    assert r.status_code == 403


def test_liaison_automatique_professeur_fiche(client, admin_token):
    from app.database import SessionLocal
    from app.models import User
    from sqlalchemy import select

    compte_email = "liaison.auto@exemple.edu"
    fiche_id = None
    try:
        # La direction crée une fiche enseignant…
        fiche = client.post(
            "/api/v1/enseignants",
            headers=h(admin_token),
            json={
                "nom": "Liaison",
                "prenom": "Auto",
                "sexe": "F",
                "tel": "0700000001",
                "email": compte_email,
                "matiere": "S1",
                "classes": [],
            },
        )
        assert fiche.status_code == 200, fiche.text
        fiche_id = fiche.json()["id"]
        # …puis un compte Professeur avec le même email : il doit être lié d'office
        compte = client.post(
            "/api/v1/auth/comptes",
            headers=h(admin_token),
            json={
                "nom": "Auto Liaison",
                "email": compte_email,
                "password": "Savoir2026!",
                "role": "Professeur",
            },
        )
        assert compte.status_code == 201, compte.text
        assert compte.json()["enseignant_id"] == fiche_id
        t = auth(client, compte_email)
        profil = client.get("/api/v1/mon-espace/profil", headers=h(t))
        assert profil.status_code == 200, profil.text
        assert profil.json()["enseignant"]["id"] == fiche_id
    finally:
        # Purge : le compte puis la fiche, pour rétablir les volumes du seed
        # (les tests de parité comptent exactement 7 enseignants).
        db = SessionLocal()
        try:
            for u in db.scalars(select(User).where(User.email == compte_email)).all():
                db.delete(u)
            db.commit()
        finally:
            db.close()
        if fiche_id:
            client.delete(f"/api/v1/enseignants/{fiche_id}", headers=h(admin_token))


def test_seul_admin_fixe_le_taux(client):
    t = auth(client, PROF)
    r = client.put(
        "/api/v1/paie/enseignants/T001/taux",
        headers=h(t),
        json={"taux_horaire": 2000},
    )
    assert r.status_code == 403


def test_administrateur_fixe_le_taux(client, admin_token):
    r = client.put(
        "/api/v1/paie/enseignants/T001/taux",
        headers=h(admin_token),
        json={"taux_horaire": 2000},
    )
    assert r.status_code == 200, r.text
    assert r.json()["tauxHoraire"] == 2000
    # Taux inconnu → 404
    n = client.put(
        "/api/v1/paie/enseignants/T999/taux",
        headers=h(admin_token),
        json={"taux_horaire": 2000},
    )
    assert n.status_code == 404


def test_bareme_visible_pour_direction(client, admin_token):
    r = client.get("/api/v1/paie/enseignants", headers=h(admin_token))
    assert r.status_code == 200, r.text
    by_id = {e["id"]: e for e in r.json()["enseignants"]}
    assert by_id["T001"]["tauxHoraire"] == 2000


def test_recap_mois_direction(client, admin_token):
    r = client.get(f"/api/v1/paie/recap?mois={_mois_courant()}", headers=h(admin_token))
    assert r.status_code == 200, r.text
    lignes = {l["enseignantId"]: l for l in r.json()["lignes"]}
    ligne = lignes["T001"]
    assert ligne["heures"] == 2.0
    assert ligne["brut"] == 4000
    assert ligne["ficheId"] is None


def test_generation_fiche_paie(client, admin_token):
    r = client.post(
        "/api/v1/paie/fiches",
        headers=h(admin_token),
        json={"mois": _mois_courant()},
    )
    assert r.status_code == 200, r.text
    compte = r.json()
    assert compte["creees"] == 1
    assert compte["sansTaux"] == []


def test_enseignant_consulte_sa_fiche(client):
    t = auth(client, PROF)
    r = client.get("/api/v1/mon-espace/fiches", headers=h(t))
    assert r.status_code == 200, r.text
    fiches = r.json()["fiches"]
    assert len(fiches) == 1
    f = fiches[0]
    assert f["mois"] == _mois_courant()
    assert f["heures"] == 2.0
    assert f["tauxHoraire"] == 2000
    assert f["brut"] == 4000
    assert f["statut"] == "en_attente"


def test_mois_cloture_par_fiche_verrouille_les_seances(client, admin_token):
    t = auth(client, PROF)
    liste = client.get(
        f"/api/v1/mon-espace/seances?mois={_mois_courant()}", headers=h(t)
    ).json()
    sid = liste["seances"][0]["id"]
    # Suppression bloquée (fiche générée)…
    r = client.delete(f"/api/v1/mon-espace/seances/{sid}", headers=h(t))
    assert r.status_code == 400
    r2 = client.delete(f"/api/v1/mon-espace/seances/{sid}", headers=h(admin_token))
    assert r2.status_code == 400


def test_fiche_payee_et_paiement_marque(client, admin_token):
    r = client.get(
        "/api/v1/mon-espace/fiches", headers=h(auth(client, PROF))
    ).json()["fiches"][0]
    fid = r["id"]
    p = client.put(
        f"/api/v1/paie/fiches/{fid}/statut",
        headers=h(admin_token),
        json={"statut": "payee"},
    )
    assert p.status_code == 200, p.text
    assert p.json()["statut"] == "payee"
    assert p.json()["payeeLe"]
    # Statut invalide → 400
    bad = client.put(
        f"/api/v1/paie/fiches/{fid}/statut",
        headers=h(admin_token),
        json={"statut": "viree"},
    )
    assert bad.status_code == 400


def test_pas_de_nouvelle_signature_sur_mois_paye(client):
    t = auth(client, PROF)
    r = _signer(client, t, heure_debut="14:00", heure_fin="16:00", classe_id="3B")
    assert r.status_code == 400
    assert "réglé" in r.json()["detail"]


def test_regeneration_ignore_les_fiches_payees(client, admin_token):
    r = client.post(
        "/api/v1/paie/fiches",
        headers=h(admin_token),
        json={"mois": _mois_courant()},
    )
    assert r.status_code == 200, r.text
    assert r.json()["payeesIgnorees"] == 1


def test_contre_passation_puis_nettoyage(client, admin_token):
    # La direction remet en attente, supprime la fiche, puis corrige le cahier.
    f = client.get(
        "/api/v1/mon-espace/fiches", headers=h(auth(client, PROF))
    ).json()["fiches"][0]
    fid = f["id"]
    enatt = client.put(
        f"/api/v1/paie/fiches/{fid}/statut",
        headers=h(admin_token),
        json={"statut": "en_attente"},
    )
    assert enatt.status_code == 200
    supp = client.delete(f"/api/v1/paie/fiches/{fid}", headers=h(admin_token))
    assert supp.status_code == 200, supp.text
    # Une fiche payée ne se supprime pas : recréer + payer + tenter
    client.post("/api/v1/paie/fiches", headers=h(admin_token), json={"mois": _mois_courant()})
    f2 = client.get(
        "/api/v1/mon-espace/fiches", headers=h(auth(client, PROF))
    ).json()["fiches"][0]
    client.put(
        f"/api/v1/paie/fiches/{f2['id']}/statut",
        headers=h(admin_token),
        json={"statut": "payee"},
    )
    verrou = client.delete(f"/api/v1/paie/fiches/{f2['id']}", headers=h(admin_token))
    assert verrou.status_code == 400
