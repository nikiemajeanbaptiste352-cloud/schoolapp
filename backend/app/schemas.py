"""Schémas Pydantic — validation des entrées/sorties de l'API.

Les formes renvoyées reflètent volontairement celles attendues par le front
(js/*.js) afin de rendre la bascule d'intégration transparente.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Authentification
# ---------------------------------------------------------------------------
class LoginIn(BaseModel):
    email: str
    password: str


class InscriptionIn(BaseModel):
    """Inscription publique — ne crée que des comptes Parent."""

    nom: str
    email: str
    password: str


class InscriptionEtablissementIn(BaseModel):
    """Inscription publique d'un établissement (rôle Administrateur).

    - ``nom`` : responsable de l'établissement qui crée le compte ;
    - ``ecole`` : nom de l'établissement, utilisé uniquement si aucune
      fiche École n'existe encore en base (bootstrap d'un déploiement).
    """

    nom: str
    email: str
    password: str
    ecole: str = ""


class CompteIn(BaseModel):
    """Création d'un compte par un administrateur (rôle au choix)."""

    nom: str
    email: str
    password: str
    role: str


class CodeDemandeIn(BaseModel):
    """Demande d'envoi d'un code de connexion par email."""

    email: str
    nom: str | None = None  # utilisé uniquement à la première création


class CodeValidationIn(BaseModel):
    """Validation d'un code reçu par email → connexion."""

    email: str
    code: str
    nom: str | None = None


class UserOut(BaseModel):
    """Profil utilisateur exposé (jamais de password_hash)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    role: str
    nom: str
    actif: bool = True
    eleve_id: str | None = None
    enseignant_id: str | None = None
    parent_id: int | None = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
    ecole: str | None = None
    annee: str | None = None


# ---------------------------------------------------------------------------
# École / informations publiques
# ---------------------------------------------------------------------------
class EcoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nom: str
    sigle: str
    slogan: str
    annee: str
    devise: str
    telephone: str
    email: str
    adresse: str
    version: str


class MessageOut(BaseModel):
    message: str


# ---------------------------------------------------------------------------
# Phase 3 — Rattachement (membres) : rôles par établissement & invitations
# ---------------------------------------------------------------------------
class MembreOut(BaseModel):
    """Rattachement exposé au front : identité + rôle **dans cette école**."""

    id: int                      # id du rattachement (`membres.id`)
    user_id: int
    nom: str
    email: str
    role: str                    # rôle effectif dans l'école courante
    statut: str                  # actif / invite / suspendu
    actif: bool = True           # compte plateforme actif
    eleve_id: str | None = None
    enseignant_id: str | None = None
    cree_le: str | None = None


class MembreInvitationIn(BaseModel):
    """Invitation / rattachement d'une adresse email à l'école courante."""

    email: str
    role: str
    nom: str | None = None


class MembreInvitationOut(BaseModel):
    """Résultat d'une invitation (le code n'est **jamais** renvoyé par l'API)."""

    id: int
    email: str
    role: str
    statut: str
    ecole: str | None = None
    expire_dans: int | None = None   # secondes avant expiration du code
    message: str
    code_envoye: bool = False        # False → aucun service email configuré


class MembreInvitationValidationIn(BaseModel):
    """Acceptation d'une invitation : le code reçu par email rattache le compte."""

    email: str
    code: str
    nom: str | None = None
    password: str | None = None


class MembreRoleIn(BaseModel):
    """Changement de rôle d'un membre (par l'administration de l'école)."""

    role: str


class MembreStatutIn(BaseModel):
    """Suspension / réactivation (actif, suspendu)."""

    statut: str


class MonEcoleOut(BaseModel):
    """Une école vue par le compte connecté (sélecteur d'établissement)."""

    school_id: int
    nom: str
    sigle: str
    role: str
    statut: str
    active: bool = False


class EcoleActiveIn(BaseModel):
    """Bascule d'établissement actif : `school_id` du rattachement visé."""

    school_id: int


# ---------------------------------------------------------------------------
# Espace enseignant — cahier de présence (séances) & rémunération
# ---------------------------------------------------------------------------
class SeanceIn(BaseModel):
    """Signature d'une séance de cours dans le cahier de présence."""

    date: str                       # "YYYY-MM-DD"
    classe_id: str
    matiere_id: str | None = None   # défaut : matière de la fiche enseignant
    heure_debut: str                # "08:00"
    heure_fin: str                  # "10:00"


class TauxIn(BaseModel):
    """Barème horaire d'un enseignant (FCFA / heure)."""

    taux_horaire: int


class MoisIn(BaseModel):
    """Mois au format AAAA-MM (ex. "2026-09")."""

    mois: str


class StatutFicheIn(BaseModel):
    """Statut d'une fiche de paie : "en_attente" ou "payee"."""

    statut: str
