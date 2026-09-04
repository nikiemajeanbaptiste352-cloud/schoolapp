"""Parité du seed — les agrégats servis par l'API doivent correspondre
exactement à ceux produits par `js/data.js` (vérifiés en navigation réelle).

Repères de parité (classe 3e A, 5 élèves : EL001, EL003, EL006, EL014, EL015) :
- Paul Kaboré EL001 : moyenne générale ~12.08/20, rang 4/5, mention « Bien ».
"""

from __future__ import annotations


def test_health_compteurs(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    counts = resp.json()["counts"]
    assert counts["classes"] == 10
    assert counts["matieres"] == 8
    assert counts["enseignants"] == 7
    assert counts["eleves"] == 15
    assert counts["annonces"] == 4


def test_bulletin_3a_parite(client, admin_token):
    from tests.conftest import h

    resp = client.get("/api/v1/classes/3A/bulletins", headers=h(admin_token))
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["classe"]["id"] == "3A"
    assert len(data["bulletins"]) == 5

    paul = next(b for b in data["bulletins"] if b["eleveId"] == "EL001")
    assert paul["nom"] == "Kaboré"
    assert paul["moyenne"] == 12.08, f"Moyenne EL001 = {paul['moyenne']}"
    assert paul["rang"]["rang"] == 4 and paul["rang"]["total"] == 5
    assert paul["mention"] == "Bien"


def test_moyennes_par_matiere_presentes(client, admin_token):
    from tests.conftest import h

    resp = client.get("/api/v1/eleves/EL001", headers=h(admin_token))
    assert resp.status_code == 200
    fiche = resp.json()
    par = fiche["resultats"]["parMatiere"]
    matieres = {p["matiereId"] for p in par}
    assert matieres == {"S1", "S2", "S3", "S4", "S5", "S6", "S7"}  # 3e : sans S8


def test_emploi_du_temps_3a(client):
    resp = client.get("/api/v1/classes/3A/emploi-du-temps")
    assert resp.status_code == 200
    grille = resp.json()["grille"]
    # 6 jours x 4 créneaux - 2 créneaux libres (mercredi + samedi, créneau 3)
    assert len(grille) == 6 * 4 - 2
    creneaux3 = [g for g in grille if g["creneau"] == 2]
    jours_creneaux3 = {g["jour"] for g in creneaux3}
    assert jours_creneaux3 == {"Lundi", "Mardi", "Jeudi", "Vendredi"}  # pas de mercredi/samedi


def test_comptes_par_role(client):
    from tests.conftest import auth

    # Professeur
    t = auth(client, "j.ouedraogo@lesavoir.edu")
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {t}"})
    assert me.json()["role"] == "Professeur"
    assert me.json()["enseignant_id"] == "T001"

    # Élève
    t2 = auth(client, "paul.kabore@lesavoir.edu")
    me2 = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {t2}"})
    assert me2.json()["role"] == "Élève"
    assert me2.json()["eleve_id"] == "EL001"


def test_mauvais_mot_de_passe(client):
    resp = client.post("/api/v1/auth/login", json={"email": "admin@lesavoir.edu", "password": "nimporte"})
    assert resp.status_code == 401


def test_etat_authentification_requise(client):
    """/etat exige un jeton (401 sinon)."""
    assert client.get("/api/v1/etat").status_code == 401


def test_etat_snapshot_complet(client, admin_token):
    """L'instantané /etat alimente le front : mêmes volumes que le seed."""
    from tests.conftest import h

    resp = client.get("/api/v1/etat", headers=h(admin_token))
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["ecole"]["nom"] == "Complexe Scolaire Privé Le Savoir"
    assert data["ecole"]["annee"] == "2026 – 2027"
    assert len(data["classes"]) == 10
    assert [c["id"] for c in data["classes"][:4]] == ["6A", "6B", "5A", "5B"]
    assert len(data["matieres"]) == 8
    assert len(data["enseignants"]) == 7
    assert len(data["eleves"]) == 15
    assert len(data["annonces"]) == 4
    assert len(data["paiements"]) == 15
    assert len(data["presences"]) == 15 * 12  # 12 semaines par élève

    # Chaque élève a ses notes (3 évals x matières de sa classe)
    eleves_ids = {e["id"] for e in data["eleves"]}
    assert {n["eleveId"] for n in data["notes"]} == eleves_ids
    assert all(n["note"] <= 20 for n in data["notes"])

    # Paiements : forme front { eleveId, motif, total, versements[] }
    p0 = data["paiements"][0]
    assert {"eleveId", "motif", "total", "versements"} <= set(p0)
    if p0["versements"]:
        assert {"montant", "date", "mode"} <= set(p0["versements"][0])
