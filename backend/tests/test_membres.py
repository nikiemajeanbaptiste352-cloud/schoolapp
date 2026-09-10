"""Tests de la Phase 3 — « Rattachement » (membres, invitations, rôles).

Trois notions sont vérifiées ici :

1. **Identité vs rôle** — un même compte peut avoir un rôle différent selon
   l'établissement (`membres.role` fait foi, `users.role` n'est qu'un repli) ;
2. **Invitation** — la direction rattache une adresse par code email, le
   compte n'est créé qu'à l'acceptation, avec le bon rôle et la bonne école ;
3. **Cloisonnement** — les routes de rattachement ne voient que l'école du
   jeton, et un identifiant d'une autre école produit un `404` (pas de fuite).

L'école n°2 (« Collège Notre-Dame de Kaya ») provient de `test_multitenant`
pour éviter de la recréer partiellement (son garde d'idempotence est global).
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.models import InvitationMembre, User
from app.services import email as email_service
from app.services.comptes import creer_user, maintenant_utc
from app.services.membres import definir_membre
from tests.conftest import auth, h
from tests.test_multitenant import EMAIL_DIR2, ecole2, token_dir2  # noqa: F401

# Code « fixe » injecté à la place du tirage aléatoire.
CODE_FIXE = "424242"
EMAIL_ADMIN1 = "admin@lesavoir.edu"
EMAIL_PROF1 = "j.ouedraogo@lesavoir.edu"
NOM_ECOLE1 = "Complexe Scolaire Privé Le Savoir"
NOM_ECOLE2 = "Collège Notre-Dame de Kaya"


# ---------------------------------------------------------------------------
# Outils
# ---------------------------------------------------------------------------
def _activer_email(monkeypatch) -> list[tuple[str, str, str, str]]:
    """Active la configuration email et capture les invitations envoyées."""
    monkeypatch.setattr(settings, "email_from", "SchoolManager <ecole@exemple.com>")
    monkeypatch.setattr(settings, "resend_api_key", "re_test_123")
    monkeypatch.setattr(settings, "smtp_host", "")
    envois: list[tuple[str, str, str, str]] = []

    def _capture_invitation(
        destinataire: str, code: str, ecole: str, role: str
    ) -> None:
        envois.append((destinataire, code, ecole, role))

    def _capture_code(destinataire: str, code: str) -> None:
        envois.append((destinataire, code, "", ""))

    def _code_fixe(longueur: int | None = None) -> str:
        return CODE_FIXE

    monkeypatch.setattr(email_service, "envoyer_invitation", _capture_invitation)
    monkeypatch.setattr(email_service, "envoyer_email_code", _capture_code)
    monkeypatch.setattr(email_service, "generer_code", _code_fixe)
    return envois


def _inviter(client, token, email: str, role: str, nom: str | None = None):
    return client.post(
        "/api/v1/membres",
        headers=h(token),
        json={"email": email, "role": role, "nom": nom},
    )


def _valider(client, email: str, code: str, nom=None, password=None):
    return client.post(
        "/api/v1/membres/invitations/valider",
        json={"email": email, "code": code, "nom": nom, "password": password},
    )


def _id_membre(client, token, email: str) -> int:
    """Identifiant de rattachement d'une adresse dans l'école du jeton."""
    r = client.get("/api/v1/membres", headers=h(token))
    assert r.status_code == 200, r.text
    for m in r.json():
        if m["email"] == email:
            return m["id"]
    raise AssertionError(f"Aucun rattachement pour {email} : {r.json()}")


def _membre_db(email: str, school_id: int) -> InvitationMembre | None:
    with SessionLocal() as db:
        return db.scalar(
            select(InvitationMembre).where(
                InvitationMembre.email == email,
                InvitationMembre.school_id == school_id,
            )
        )


def _compte_db(email: str) -> tuple[int, str, int | None, str | None] | None:
    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.email == email))
        if u is None:
            return None
        return (u.id, u.role, u.school_id, u.enseignant_id)


# ---------------------------------------------------------------------------
# 1. Remplissage automatique : les comptes existants sont des membres actifs
# ---------------------------------------------------------------------------
def test_comptes_existants_rattaches_automatiquement(client, admin_token):
    """Le premier appel remplit `membres` depuis `users` (idempotent)."""
    r = client.get("/api/v1/membres", headers=h(admin_token))
    assert r.status_code == 200, r.text
    par_email = {m["email"]: m for m in r.json()}

    assert EMAIL_ADMIN1 in par_email
    admin = par_email[EMAIL_ADMIN1]
    assert admin["role"] == "Administrateur"
    assert admin["statut"] == "actif"
    assert admin["actif"] is True
    assert admin["id"] > 0 and admin["user_id"] > 0

    # La fiche métier reste liée au rattachement (aucune régression du seed).
    assert par_email[EMAIL_PROF1]["enseignant_id"] == "T001"
    assert par_email[EMAIL_PROF1]["role"] == "Professeur"

    # Second appel : aucun doublon (idempotence).
    assert len(client.get("/api/v1/membres", headers=h(admin_token)).json()) == len(
        par_email
    )


def test_liste_membres_reservee_a_la_direction(client):
    """Professeur et Élève n'administrent pas les rattachements."""
    for email in (EMAIL_PROF1, "paul.kabore@lesavoir.edu"):
        t = auth(client, email)
        assert client.get("/api/v1/membres", headers=h(t)).status_code == 403
        assert (
            client.get("/api/v1/membres/invitations", headers=h(t)).status_code == 403
        )
        assert (
            _inviter(client, t, "intrus.rattachement@exemple-membres.edu", "Parent")
            .status_code
            == 403
        )


# ---------------------------------------------------------------------------
# 2. Cloisonnement : on ne voit que les membres de SON établissement
# ---------------------------------------------------------------------------
def test_membres_isoles_par_ecole(client, admin_token, token_dir2, ecole2):
    e1 = {m["email"] for m in client.get("/api/v1/membres", headers=h(admin_token)).json()}
    e2 = {m["email"] for m in client.get("/api/v1/membres", headers=h(token_dir2)).json()}

    assert EMAIL_ADMIN1 in e1 and EMAIL_ADMIN1 not in e2
    assert EMAIL_DIR2 in e2 and EMAIL_DIR2 not in e1
    assert e1 & e2 == set()

    # Un identifiant de l'école 1 manipulé depuis l'école 2 → 404 (pas de fuite).
    id1 = _id_membre(client, admin_token, EMAIL_ADMIN1)
    for methode, url, corps in (
        ("put", f"/api/v1/membres/{id1}/role", {"role": "Surveillant"}),
        ("put", f"/api/v1/membres/{id1}/statut", {"statut": "suspendu"}),
        ("delete", f"/api/v1/membres/{id1}", None),
    ):
        appel = getattr(client, methode)
        r = appel(url, headers=h(token_dir2), json=corps) if corps else appel(
            url, headers=h(token_dir2)
        )
        assert r.status_code == 404, f"{methode} {url} → {r.status_code}"


# ---------------------------------------------------------------------------
# 3. Invitation : aucun compte créé avant l'acceptation
# ---------------------------------------------------------------------------
def test_invitation_cree_un_rattachement_en_attente(client, admin_token, monkeypatch):
    envois = _activer_email(monkeypatch)
    email = "invite.prof@exemple-membres.edu"

    r = _inviter(client, admin_token, email, "Professeur", "Invitée Prof")
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["statut"] == "invite"
    assert data["role"] == "Professeur"
    assert data["ecole"] == NOM_ECOLE1
    assert data["code_envoye"] is True
    assert data["expire_dans"] == settings.code_expire_minutes * 60

    # Le code part par email, jamais par l'API.
    assert envois == [(email, CODE_FIXE, NOM_ECOLE1, "Professeur")]
    assert CODE_FIXE not in r.text

    # Aucun compte n'est créé à ce stade.
    assert _compte_db(email) is None
    ligne = _membre_db(email, 1)
    assert ligne is not None and ligne.role == "Professeur"
    assert ligne.tentatives == 0 and ligne.invite_par is not None

    # L'invitation est visible côté direction (file d'attente).
    invits = client.get("/api/v1/membres/invitations", headers=h(admin_token)).json()
    assert [i for i in invits if i["email"] == email and i["statut"] == "invite"]


def test_invitation_sans_service_email_refusee(client, admin_token):
    """Sans fournisseur configuré, l'invitation est refusée (503)."""
    email = "sans.service.membre@exemple-membres.edu"
    r = _inviter(client, admin_token, email, "Surveillant")
    assert r.status_code == 503
    assert _membre_db(email, 1) is None


def test_invitation_role_invalide_refusee(client, admin_token, monkeypatch):
    _activer_email(monkeypatch)
    r = _inviter(client, admin_token, "role.invalide@exemple-membres.edu", "SuperAdmin")
    assert r.status_code == 422
    assert "Rôle invalide" in r.json()["detail"]


def test_invitation_adresse_deja_membre_refusee(client, admin_token, monkeypatch):
    """Un membre actif ne peut pas être « invité » (et n'est pas rétrogradé)."""
    _activer_email(monkeypatch)
    r = _inviter(client, admin_token, EMAIL_PROF1, "Surveillant")
    assert r.status_code == 409

    # Le rattachement du professeur reste actif avec son rôle d'origine.
    membres = client.get("/api/v1/membres", headers=h(admin_token)).json()
    prof = [m for m in membres if m["email"] == EMAIL_PROF1][0]
    assert prof["role"] == "Professeur" and prof["statut"] == "actif"


def test_invitation_anti_spam(client, admin_token, monkeypatch):
    """Deux invitations < 60 s pour la même adresse → 429."""
    _activer_email(monkeypatch)
    email = "anti.spam.membre@exemple-membres.edu"
    assert _inviter(client, admin_token, email, "Parent").status_code == 201
    assert _inviter(client, admin_token, email, "Parent").status_code == 429


# ---------------------------------------------------------------------------
# 4. Acceptation de l'invitation : compte créé + rôle activé
# ---------------------------------------------------------------------------
def test_validation_invitation_cree_compte_et_role(client, admin_token, monkeypatch):
    envois = _activer_email(monkeypatch)
    email = "invite.eleve@exemple-membres.edu"

    assert _inviter(client, admin_token, email, "Élève", "Invitée Élève").status_code == 201
    assert envois and envois[-1][1] == CODE_FIXE

    r = _valider(client, email, CODE_FIXE, nom="Invitée Élève", password="Sesame2026!")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["access_token"]
    assert data["user"]["email"] == email
    assert data["user"]["role"] == "Élève"
    assert data["user"]["nom"] == "Invitée Élève"
    assert data["ecole"] == NOM_ECOLE1

    # Le compte existe, rattaché à l'école de l'invitation, rôle « Élève ».
    compte = _compte_db(email)
    assert compte is not None
    _, role, school_id, _ = compte
    assert (role, school_id) == ("Élève", 1)

    # Le jeton du nouveau compte fonctionne (puis il est rattaché/actif).
    t = data["access_token"]
    me = client.get("/api/v1/auth/me", headers=h(t))
    assert me.status_code == 200, me.text
    assert me.json()["role"] == "Élève"

    # Le mot de passe choisi à l'acceptation permet la connexion classique.
    login = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "Sesame2026!"}
    )
    assert login.status_code == 200, login.text

    # Rattachement actif visible côté direction.
    membres = client.get("/api/v1/membres", headers=h(admin_token)).json()
    nouveau = [m for m in membres if m["email"] == email][0]
    assert nouveau["role"] == "Élève" and nouveau["statut"] == "actif"

    # Usage unique : le code est consommé.
    encore = _valider(client, email, CODE_FIXE)
    assert encore.status_code == 401
    assert _membre_db(email, 1) is None


def test_validation_invitation_mauvais_code(client, admin_token, monkeypatch):
    """Mauvais code → 401, mais le bon code reste utilisable (tentative comptée)."""
    _activer_email(monkeypatch)
    email = "mauvais.code.membre@exemple-membres.edu"
    assert _inviter(client, admin_token, email, "Surveillant").status_code == 201

    assert _valider(client, email, "000000").status_code == 401
    assert _valider(client, email, "999999").status_code == 401

    r = _valider(client, email, CODE_FIXE, nom="Tentatif", password="Sesame2026!")
    assert r.status_code == 200, r.text
    assert r.json()["user"]["role"] == "Surveillant"


def test_validation_invitation_expiree(client, admin_token, monkeypatch):
    _activer_email(monkeypatch)
    email = "expiree.membre@exemple-membres.edu"
    assert _inviter(client, admin_token, email, "Parent").status_code == 201

    # On fait expirer le code en base directement.
    with SessionLocal() as db:
        ligne = db.scalar(
            select(InvitationMembre).where(InvitationMembre.email == email)
        )
        ligne.expires_at = maintenant_utc() - timedelta(minutes=1)
        db.commit()

    r = _valider(client, email, CODE_FIXE)
    assert r.status_code == 401
    assert "expir" in r.json()["detail"].lower()

    invits = client.get("/api/v1/membres/invitations", headers=h(admin_token)).json()
    assert [i for i in invits if i["email"] == email and i["statut"] == "expire"]


def test_validation_invitation_sans_invitation(client):
    r = _valider(client, "jamais.invite@exemple-membres.edu", CODE_FIXE)
    assert r.status_code == 401
    assert "Aucune invitation" in r.json()["detail"]


# ---------------------------------------------------------------------------
# 5. Suspension : le rattachement coupe l'accès sans supprimer l'identité
# ---------------------------------------------------------------------------
def test_suspension_puis_reactivation(client, admin_token, monkeypatch):
    _activer_email(monkeypatch)
    email = "surveillant.suspendu@exemple-membres.edu"
    assert _inviter(client, admin_token, email, "Surveillant", "Surv Suspendu").status_code == 201
    valide = _valider(client, email, CODE_FIXE, nom="Surv Suspendu", password="Sesame2026!")
    assert valide.status_code == 200, valide.text
    t = valide.json()["access_token"]
    assert client.get("/api/v1/auth/me", headers=h(t)).status_code == 200

    id_membre = _id_membre(client, admin_token, email)

    sus = client.put(
        f"/api/v1/membres/{id_membre}/statut",
        headers=h(admin_token),
        json={"statut": "suspendu"},
    )
    assert sus.status_code == 200, sus.text
    assert sus.json()["statut"] == "suspendu"

    # Le jeton existant est refusé : le rattachement fait foi.
    bloque = client.get("/api/v1/auth/me", headers=h(t))
    assert bloque.status_code == 403
    assert "suspendu" in bloque.json()["detail"].lower()
    # Le compte plateforme, lui, reste intact.
    assert _compte_db(email) is not None

    reac = client.put(
        f"/api/v1/membres/{id_membre}/statut",
        headers=h(admin_token),
        json={"statut": "actif"},
    )
    assert reac.status_code == 200
    assert client.get("/api/v1/auth/me", headers=h(t)).status_code == 200


def test_dernier_administrateur_protege(client, token_dir2, ecole2):
    """L'école n°2 n'a qu'un admin : suspension, changement de rôle et
    suppression sont refusés tant qu'il reste le seul."""
    id_admin2 = _id_membre(client, token_dir2, EMAIL_DIR2)

    sus = client.put(
        f"/api/v1/membres/{id_admin2}/statut",
        headers=h(token_dir2),
        json={"statut": "suspendu"},
    )
    assert sus.status_code == 400
    assert "dernier" in sus.json()["detail"].lower()

    role = client.put(
        f"/api/v1/membres/{id_admin2}/role",
        headers=h(token_dir2),
        json={"role": "Surveillant"},
    )
    assert role.status_code == 400

    sup = client.delete(f"/api/v1/membres/{id_admin2}", headers=h(token_dir2))
    assert sup.status_code == 400

    # Toujours admin actif : l'ordre des opérations ne l'a pas cassé.
    membres = client.get("/api/v1/membres", headers=h(token_dir2)).json()
    admin2 = [m for m in membres if m["email"] == EMAIL_DIR2][0]
    assert admin2["role"] == "Administrateur" and admin2["statut"] == "actif"


def test_changement_de_role_miroir_utilisateur(client, admin_token, monkeypatch):
    """Changer le rôle du rattachement met à jour le rôle effectif du compte."""
    _activer_email(monkeypatch)
    email = "role.change@exemple-membres.edu"
    assert _inviter(client, admin_token, email, "Parent", "Role Change").status_code == 201
    valide = _valider(client, email, CODE_FIXE, nom="Role Change", password="Sesame2026!")
    t = valide.json()["access_token"]
    assert valide.json()["user"]["role"] == "Parent"
    assert client.get("/api/v1/membres", headers=h(t)).status_code == 403

    id_membre = _id_membre(client, admin_token, email)
    r = client.put(
        f"/api/v1/membres/{id_membre}/role",
        headers=h(admin_token),
        json={"role": "Surveillant"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "Surveillant"
    # Rôle effectif mis à jour pour le compte.
    me = client.get("/api/v1/auth/me", headers=h(t))
    assert me.json()["role"] == "Surveillant"

    # Rôle inconnu → 422 (y compris sur son propre rattachement).
    id_admin = _id_membre(client, admin_token, EMAIL_ADMIN1)
    assert (
        client.put(
            f"/api/v1/membres/{id_admin}/role",
            headers=h(admin_token),
            json={"role": "SuperAdmin"},
        ).status_code
        == 422
    )


def test_statut_invalide_refuse(client, admin_token):
    """`invite` n'est pas manipulable à la main (422)."""
    id_admin = _id_membre(client, admin_token, EMAIL_ADMIN1)
    r = client.put(
        f"/api/v1/membres/{id_admin}/statut",
        headers=h(admin_token),
        json={"statut": "invite"},
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# 6. Multi-rattachement : sélecteur d'établissement et bascule
# ---------------------------------------------------------------------------
EMAIL_MULTI = "multi.rattachement@exemple-membres.edu"


def _creer_compte_multi() -> int:
    """Compte de test : actif dans l'école 1 (Parent) et l'école 2 (Surveillant)."""
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == EMAIL_MULTI))
        if user is None:
            user = creer_user(db, "Multi Rattachement", EMAIL_MULTI, "Savoir2026!", "Parent", school_id=1)
        definir_membre(db, user, 1, "Parent", "actif")
        definir_membre(db, user, 2, "Surveillant", "actif")
        db.commit()
        return user.id


def test_selecteur_et_bascule_d_etablissement(client, admin_token, token_dir2, ecole2):
    _creer_compte_multi()
    t = auth(client, EMAIL_MULTI)

    ecoles = client.get("/api/v1/mon-espace/ecoles", headers=h(t))
    assert ecoles.status_code == 200, ecoles.text
    par_id = {e["school_id"]: e for e in ecoles.json()}
    assert set(par_id) == {1, 2}
    assert par_id[1]["nom"] == NOM_ECOLE1
    assert par_id[1]["sigle"] == "CSP Le Savoir"
    assert par_id[1]["role"] == "Parent"
    assert par_id[1]["statut"] == "actif" and par_id[1]["active"] is True
    assert par_id[2]["nom"] == NOM_ECOLE2
    assert par_id[2]["role"] == "Surveillant" and par_id[2]["active"] is False

    # Bascule : nouveau jeton, nouveau rôle, nouvelle école.
    bascule = client.post(
        "/api/v1/mon-espace/ecole-active", headers=h(t), json={"school_id": 2}
    )
    assert bascule.status_code == 200, bascule.text
    data = bascule.json()
    assert data["user"]["role"] == "Surveillant"
    assert data["ecole"] == NOM_ECOLE2
    t2 = data["access_token"]

    # Le rôle est bien celui du rattachement : Surveillant, pas Administrateur.
    assert client.get("/api/v1/ecole", headers=h(t2)).json()["nom"] == NOM_ECOLE2
    assert client.get("/api/v1/membres", headers=h(t2)).status_code == 403

    # Établissement sans rattachement → 404 (pas d'énumération).
    assert (
        client.post(
            "/api/v1/mon-espace/ecole-active", headers=h(t2), json={"school_id": 3}
        ).status_code
        == 404
    )

    # Retour à l'école 1.
    retour = client.post(
        "/api/v1/mon-espace/ecole-active", headers=h(t2), json={"school_id": 1}
    )
    assert retour.status_code == 200, retour.text
    assert retour.json()["user"]["role"] == "Parent"
    assert retour.json()["ecole"] == NOM_ECOLE1


def test_retrait_membre_et_repli_ecole(client, admin_token, token_dir2, ecole2):
    """Retirer un rattachement non actif est permis ; le dernier est protégé."""
    from app.models import Membership

    _creer_compte_multi()

    # Le compte travaille dans l'école 1 : le retirer de l'école 2 est permis.
    id2 = _id_membre(client, token_dir2, EMAIL_MULTI)
    r = client.delete(f"/api/v1/membres/{id2}", headers=h(token_dir2))
    assert r.status_code == 200, r.text

    t = auth(client, EMAIL_MULTI)
    ecoles = client.get("/api/v1/mon-espace/ecoles", headers=h(t)).json()
    assert [e["school_id"] for e in ecoles] == [1]

    # Le dernier rattachement ne peut pas être supprimé → suspendre à la place.
    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.email == EMAIL_MULTI))
        membre1 = db.scalar(
            select(Membership).where(
                Membership.user_id == u.id, Membership.school_id == 1
            )
        )
        id_membre1 = membre1.id

    refus = client.delete(f"/api/v1/membres/{id_membre1}", headers=h(admin_token))
    assert refus.status_code == 400
    assert "suspend" in refus.json()["detail"].lower()

    # La suspension, elle, passe et coupe l'accès sans supprimer l'identité.
    sus = client.put(
        f"/api/v1/membres/{id_membre1}/statut",
        headers=h(admin_token),
        json={"statut": "suspendu"},
    )
    assert sus.status_code == 200, sus.text
    bloque = client.get("/api/v1/auth/me", headers=h(t))
    assert bloque.status_code == 403
    assert _compte_db(EMAIL_MULTI) is not None


# ---------------------------------------------------------------------------
# Annulation d'une invitation (suppression du code)
# ---------------------------------------------------------------------------
def test_annulation_invitation(client, admin_token, token_dir2, monkeypatch):
    """`DELETE /membres/invitations/{id}` révoque le code, sans fuite inter-écoles."""
    envois = _activer_email(monkeypatch)

    email = "invite.annule@lesavoir.edu"
    r = _inviter(client, admin_token, email, "Surveillant")
    assert r.status_code == 201, r.text
    id_invitation = r.json()["id"]
    assert _membre_db(email, 1) is not None

    # Une autre école ne peut pas annuler l'invitation : même 404 (pas de fuite).
    intrus = client.delete(
        f"/api/v1/membres/invitations/{id_invitation}", headers=h(token_dir2)
    )
    assert intrus.status_code == 404
    assert _membre_db(email, 1) is not None

    # 404 aussi pour un identifiant inexistant.
    assert client.delete(
        "/api/v1/membres/invitations/999999", headers=h(admin_token)
    ).status_code == 404

    # L'annulation par la bonne école supprime le code…
    ok = client.delete(
        f"/api/v1/membres/invitations/{id_invitation}", headers=h(admin_token)
    )
    assert ok.status_code == 200, ok.text
    assert email in ok.json()["message"]
    assert _membre_db(email, 1) is None

    # … et la validation du code devient impossible.
    assert _valider(client, email, CODE_FIXE, nom="Invité Annulé").status_code == 401
    assert _compte_db(email) is None

    # Le rattachement resté en attente est révoqué lui aussi.
    r2 = client.get("/api/v1/membres", headers=h(admin_token))
    assert email not in [m["email"] for m in r2.json()]

    # Un nouveau cycle d'invitation reste possible (l'anti-spam est reparti).
    encore = _inviter(client, admin_token, email, "Parent")
    assert encore.status_code == 201, encore.text
    assert len(envois) >= 2
