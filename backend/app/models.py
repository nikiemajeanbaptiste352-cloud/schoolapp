"""Modèles SQLAlchemy — miroir relationnel de `js/data.js` (window.SD).

Multi-établissements (Phase 2 — isolation school_id) :
- `ecole` devient le registre des établissements ; chaque école a un `id`
  entier (clé de locataire → `school_id` sur toutes les tables de domaine).
- Les tables à codes métier lisibles conservent leurs codes exacts
  ("3A", "S1", "T001", "EL001", "A1"…) mais leur clé primaire devient
  composite `(school_id, id)` : le même code peut exister dans deux écoles.
- `users` reste une identité plateforme ; `users.school_id` est un
  rattachement transitoire en attendant la table `memberships` (Phase 3).
- `notes`, `presences`, `paiements`, `versements`, `parents`, `seances`…
  gardent des PK entières auto-générées + colonne `school_id`.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    PrimaryKeyConstraint,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# ---------------------------------------------------------------
# Tables d'association M:N
# ---------------------------------------------------------------
classe_matiere = Table(
    "classe_matiere",
    Base.metadata,
    Column("school_id", ForeignKey("ecole.id"), primary_key=True),
    Column("classe_id", String(6), primary_key=True),
    Column("matiere_id", String(6), primary_key=True),
    Column("ordre", Integer, default=0),  # ordre d'affichage
    ForeignKeyConstraint(
        ["school_id", "classe_id"],
        ["classes.school_id", "classes.id"],
    ),
    ForeignKeyConstraint(
        ["school_id", "matiere_id"],
        ["matieres.school_id", "matieres.id"],
    ),
)

enseignant_classe = Table(
    "enseignant_classe",
    Base.metadata,
    Column("school_id", ForeignKey("ecole.id"), primary_key=True),
    Column("enseignant_id", String(6), primary_key=True),
    Column("classe_id", String(6), primary_key=True),
    ForeignKeyConstraint(
        ["school_id", "enseignant_id"],
        ["enseignants.school_id", "enseignants.id"],
    ),
    ForeignKeyConstraint(
        ["school_id", "classe_id"],
        ["classes.school_id", "classes.id"],
    ),
)


# ---------------------------------------------------------------
# École (singleton)
# ---------------------------------------------------------------
class Ecole(Base):
    __tablename__ = "ecole"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nom: Mapped[str] = mapped_column(String(120))
    sigle: Mapped[str] = mapped_column(String(60))
    slogan: Mapped[str] = mapped_column(String(160))
    annee: Mapped[str] = mapped_column(String(20))          # "2026 – 2027"
    devise: Mapped[str] = mapped_column(String(10))         # "FCFA"
    telephone: Mapped[str] = mapped_column(String(30))
    email: Mapped[str] = mapped_column(String(80))
    adresse: Mapped[str] = mapped_column(String(160))
    version: Mapped[str] = mapped_column(String(10))


# ---------------------------------------------------------------
# Matières — PK (school_id, id)
# ---------------------------------------------------------------
class Matiere(Base):
    __tablename__ = "matieres"

    school_id: Mapped[int] = mapped_column(
        ForeignKey("ecole.id"), primary_key=True
    )
    id: Mapped[str] = mapped_column(String(6), primary_key=True)   # "S1"…
    nom: Mapped[str] = mapped_column(String(60))
    coef: Mapped[int] = mapped_column(Integer)
    icone: Mapped[str] = mapped_column(String(6))
    couleur: Mapped[str] = mapped_column(String(20))

    enseignants: Mapped[list["Enseignant"]] = relationship(back_populates="matiere")
    classes: Mapped[list["Classe"]] = relationship(
        secondary=classe_matiere, back_populates="matieres",
        order_by=classe_matiere.c.ordre,
    )


# ---------------------------------------------------------------
# Classes — PK (school_id, id)
# ---------------------------------------------------------------
class Classe(Base):
    __tablename__ = "classes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["school_id", "principal_id"],
            ["enseignants.school_id", "enseignants.id"],
        ),
    )

    school_id: Mapped[int] = mapped_column(
        ForeignKey("ecole.id"), primary_key=True
    )
    id: Mapped[str] = mapped_column(String(6), primary_key=True)   # "6A", "3B"…
    nom: Mapped[str] = mapped_column(String(20))
    cycle: Mapped[str] = mapped_column(String(10))                  # Collège / Lycée
    salle: Mapped[str] = mapped_column(String(20))
    principal_id: Mapped[str | None] = mapped_column(String(6), nullable=True)

    principal: Mapped["Enseignant | None"] = relationship(
        foreign_keys="[Classe.school_id, Classe.principal_id]",
        back_populates="classes_principales",
    )
    eleves: Mapped[list["Eleve"]] = relationship(back_populates="classe")
    matieres: Mapped[list[Matiere]] = relationship(
        secondary=classe_matiere, back_populates="classes",
        order_by=classe_matiere.c.ordre,
    )
    enseignants: Mapped[list["Enseignant"]] = relationship(
        secondary=enseignant_classe, back_populates="classes"
    )


# ---------------------------------------------------------------
# Enseignants — PK (school_id, id)
# ---------------------------------------------------------------
class Enseignant(Base):
    __tablename__ = "enseignants"
    __table_args__ = (
        ForeignKeyConstraint(
            ["school_id", "matiere_id"],
            ["matieres.school_id", "matieres.id"],
        ),
    )

    school_id: Mapped[int] = mapped_column(
        ForeignKey("ecole.id"), primary_key=True
    )
    id: Mapped[str] = mapped_column(String(6), primary_key=True)    # "T001"…
    nom: Mapped[str] = mapped_column(String(40))
    prenom: Mapped[str] = mapped_column(String(40))
    sexe: Mapped[str] = mapped_column(String(1))
    tel: Mapped[str] = mapped_column(String(20))
    email: Mapped[str] = mapped_column(String(80))
    matiere_id: Mapped[str | None] = mapped_column(String(6), nullable=True)
    statut: Mapped[str] = mapped_column(String(10), default="Actif")

    matiere: Mapped[Matiere | None] = relationship(back_populates="enseignants")
    classes: Mapped[list[Classe]] = relationship(
        secondary=enseignant_classe, back_populates="enseignants"
    )
    classes_principales: Mapped[list[Classe]] = relationship(
        foreign_keys="[Classe.school_id, Classe.principal_id]",
        back_populates="principal",
    )


# ---------------------------------------------------------------
# Parents — PK entière (id), scopés par school_id
# ---------------------------------------------------------------
class Parent(Base):
    __tablename__ = "parents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    school_id: Mapped[int] = mapped_column(
        ForeignKey("ecole.id"), nullable=False, default=1
    )
    nom: Mapped[str] = mapped_column(String(80))
    lien: Mapped[str] = mapped_column(String(20))       # Père / Mère…
    tel: Mapped[str] = mapped_column(String(20))
    email: Mapped[str] = mapped_column(String(80))
    profession: Mapped[str] = mapped_column(String(40))
    adresse: Mapped[str] = mapped_column(String(80))

    enfants: Mapped[list["Eleve"]] = relationship(back_populates="parent")


# ---------------------------------------------------------------
# Élèves — PK (school_id, id)
# ---------------------------------------------------------------
class Eleve(Base):
    __tablename__ = "eleves"
    __table_args__ = (
        ForeignKeyConstraint(
            ["school_id", "classe_id"],
            ["classes.school_id", "classes.id"],
        ),
    )

    school_id: Mapped[int] = mapped_column(
        ForeignKey("ecole.id"), primary_key=True
    )
    id: Mapped[str] = mapped_column(String(6), primary_key=True)    # "EL001"…
    nom: Mapped[str] = mapped_column(String(40))
    prenom: Mapped[str] = mapped_column(String(40))
    sexe: Mapped[str] = mapped_column(String(1))                    # M / F
    naissance: Mapped[date] = mapped_column(Date)
    classe_id: Mapped[str] = mapped_column(String(6))
    statut: Mapped[str] = mapped_column(String(10), default="Actif")
    inscription: Mapped[date] = mapped_column(Date)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("parents.id"), nullable=True
    )

    classe: Mapped[Classe] = relationship(back_populates="eleves")
    parent: Mapped[Parent | None] = relationship(back_populates="enfants")
    notes: Mapped[list["Note"]] = relationship(
        back_populates="eleve", cascade="all, delete-orphan"
    )
    presences: Mapped[list["Presence"]] = relationship(
        back_populates="eleve", cascade="all, delete-orphan"
    )
    paiements: Mapped[list["Paiement"]] = relationship(
        back_populates="eleve", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------
# Notes (scopées par school_id)
# ---------------------------------------------------------------
class Note(Base):
    __tablename__ = "notes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["school_id", "eleve_id"],
            ["eleves.school_id", "eleves.id"],
        ),
        ForeignKeyConstraint(
            ["school_id", "matiere_id"],
            ["matieres.school_id", "matieres.id"],
        ),
        UniqueConstraint(
            "school_id", "eleve_id", "matiere_id", "eval",
            name="uq_note_eleve_matiere_eval",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    school_id: Mapped[int] = mapped_column(
        ForeignKey("ecole.id"), nullable=False, default=1
    )
    eleve_id: Mapped[str] = mapped_column(String(6))
    matiere_id: Mapped[str] = mapped_column(String(6))
    eval: Mapped[str] = mapped_column(String(20))       # Devoir 1 / Devoir 2 / Composition
    note: Mapped[float] = mapped_column(Float)          # 0 → 20, pas de 0,5

    eleve: Mapped[Eleve] = relationship(back_populates="notes")
    matiere: Mapped[Matiere] = relationship(
        overlaps="eleve,notes"  # school_id copié par les deux parents → même école
    )


# ---------------------------------------------------------------
# Présences (scopées par school_id)
# ---------------------------------------------------------------
class Presence(Base):
    __tablename__ = "presences"
    __table_args__ = (
        ForeignKeyConstraint(
            ["school_id", "eleve_id"],
            ["eleves.school_id", "eleves.id"],
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    school_id: Mapped[int] = mapped_column(
        ForeignKey("ecole.id"), nullable=False, default=1
    )
    eleve_id: Mapped[str] = mapped_column(String(6))
    date: Mapped[date] = mapped_column(Date)
    statut: Mapped[str] = mapped_column(String(1))      # P / R / A

    eleve: Mapped[Eleve] = relationship(back_populates="presences")


# ---------------------------------------------------------------
# Paiements (dossier) + Versements (scopés par school_id)
# ---------------------------------------------------------------
class Paiement(Base):
    __tablename__ = "paiements"
    __table_args__ = (
        ForeignKeyConstraint(
            ["school_id", "eleve_id"],
            ["eleves.school_id", "eleves.id"],
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    school_id: Mapped[int] = mapped_column(
        ForeignKey("ecole.id"), nullable=False, default=1
    )
    eleve_id: Mapped[str] = mapped_column(String(6))
    motif: Mapped[str] = mapped_column(String(120))
    total: Mapped[int] = mapped_column(Integer)

    eleve: Mapped[Eleve] = relationship(back_populates="paiements")
    versements: Mapped[list["Versement"]] = relationship(
        back_populates="paiement", cascade="all, delete-orphan",
        order_by="Versement.date",
    )


class Versement(Base):
    __tablename__ = "versements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    school_id: Mapped[int] = mapped_column(
        ForeignKey("ecole.id"), nullable=False, default=1
    )
    paiement_id: Mapped[int] = mapped_column(ForeignKey("paiements.id"))
    montant: Mapped[int] = mapped_column(Integer)
    date: Mapped[date] = mapped_column(Date)
    mode: Mapped[str] = mapped_column(String(20))       # Espèces / Mobile Money / Chèque

    paiement: Mapped[Paiement] = relationship(back_populates="versements")


# ---------------------------------------------------------------
# Annonces — PK (school_id, id)
# ---------------------------------------------------------------
class Annonce(Base):
    __tablename__ = "annonces"

    school_id: Mapped[int] = mapped_column(
        ForeignKey("ecole.id"), primary_key=True
    )
    id: Mapped[str] = mapped_column(String(6), primary_key=True)    # "A1"…
    titre: Mapped[str] = mapped_column(String(120))
    contenu: Mapped[str] = mapped_column(Text)
    categorie: Mapped[str] = mapped_column(String(30))
    date: Mapped[date] = mapped_column(Date)
    auteur: Mapped[str] = mapped_column(String(60))
    important: Mapped[bool] = mapped_column(Boolean, default=False)


# ---------------------------------------------------------------
# Comptes utilisateurs (Phase 2 — auth)
# ---------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))       # Administrateur / Professeur / Élève / Parent
    nom: Mapped[str] = mapped_column(String(80))
    actif: Mapped[bool] = mapped_column(Boolean, default=True)
    # Établissement de rattachement principal
    # (transitoire : la table `memberships`, Phase 3, remplacera cette colonne)
    school_id: Mapped[int | None] = mapped_column(
        ForeignKey("ecole.id"), nullable=True
    )
    # Liaisons optionnelles vers la personne physique (codes de l'école liée)
    eleve_id: Mapped[str | None] = mapped_column(String(6), nullable=True)
    enseignant_id: Mapped[str | None] = mapped_column(String(6), nullable=True)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("parents.id"), nullable=True
    )


# ---------------------------------------------------------------
# Rattachements à un établissement (Phase 3 — « membres »)
# ---------------------------------------------------------------
# Modèle aligné sur les trois notions de l'architecture cible :
#   identité (`users`) / rôle fonctionnel (`membres.role`, **par école**) /
#   permissions (règles de l'API).
# Une même identité peut donc être Professeur dans l'école 1 et Parent dans
# l'école 2 : `user.role`/`user.school_id` restent en base pour la compatibilité
# mais la source de vérité devient cette table.
ROLES_MEMBRE = ("Administrateur", "Professeur", "Surveillant", "Élève", "Parent")
STATUTS_MEMBRE = ("actif", "invite", "suspendu")


def _roles_membre_sql() -> str:
    """Liste SQL des rôles autorisés (portable SQLite / PostgreSQL)."""
    litteraux = ", ".join(f"'{r}'" for r in ROLES_MEMBRE)
    return f"role IN ({litteraux})"


class Membership(Base):
    """Rattachement d'une identité à un établissement (`membres`).

    `statut` :
      - `actif`    → accès autorisé ;
      - `invite`   → invitation envoyée, en attente d'acceptation ;
      - `suspendu` → accès refusé (403) mais rattachement conservé.
    """

    __tablename__ = "membres"
    __table_args__ = (
        UniqueConstraint("user_id", "school_id", name="uq_membre_user_ecole"),
        CheckConstraint(_roles_membre_sql(), name="ck_membre_role"),
        CheckConstraint(
            "statut IN ('actif', 'invite', 'suspendu')", name="ck_membre_statut"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), index=True
    )
    school_id: Mapped[int] = mapped_column(
        ForeignKey("ecole.id"), index=True
    )
    role: Mapped[str] = mapped_column(String(20))
    statut: Mapped[str] = mapped_column(String(12), default="actif")
    cree_le: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    # Compte de l'école qui a émis l'invitation (traçabilité, nullable)
    invite_par: Mapped[int | None] = mapped_column(Integer, nullable=True)


class InvitationMembre(Base):
    """Invitation d'une adresse email à rejoindre une école (`membres_invitations`).

    Miroir de `EmailCode` (code à 6 chiffres haché HMAC, usage unique, délai
    d'expiration, compteur de tentatives) pour que l'invité valide son
    rattachement avec le même mécanisme que la connexion par email.
    """

    __tablename__ = "membres_invitations"
    __table_args__ = (
        UniqueConstraint("school_id", "email", name="uq_invitation_ecole_email"),
        CheckConstraint(_roles_membre_sql(), name="ck_invitation_role"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    school_id: Mapped[int] = mapped_column(ForeignKey("ecole.id"), index=True)
    email: Mapped[str] = mapped_column(String(80), index=True)
    role: Mapped[str] = mapped_column(String(20))
    code_hash: Mapped[str] = mapped_column(String(128))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    tentatives: Mapped[int] = mapped_column(Integer, default=0)
    invite_par: Mapped[int | None] = mapped_column(Integer, nullable=True)


# ---------------------------------------------------------------
# Codes de connexion par email (Phase 4 — connexion sans mot de passe)
# ---------------------------------------------------------------
class EmailCode(Base):
    """Code à 6 chiffres, à usage unique, envoyé par email.

    Une seule ligne active par email (clé primaire = email). Le code est
    stocké haché (HMAC-SHA256 avec la SECRET_KEY) ; seule sa date d'expiration
    et le compteur de tentatives sont conservés en clair.
    """

    __tablename__ = "email_codes"

    email: Mapped[str] = mapped_column(String(80), primary_key=True)
    code_hash: Mapped[str] = mapped_column(String(128))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    tentatives: Mapped[int] = mapped_column(Integer, default=0)


# ---------------------------------------------------------------
# Espace enseignant — cahier de présence (signatures) & rémunération
# ---------------------------------------------------------------
# Notes de conception :
# - Le barème est stocké dans une table dédiée (et non en colonne de
#   `enseignants`) pour rester compatible avec des bases déjà créées
#   (create_all n'ajoute jamais de colonne sur une table existante).
# - Chaque signature de séance est horodatée (le « cahier » papier numérisé).
# - Les fiches de paie sont générées par la direction et figent les heures
#   réellement données ainsi que le taux appliqué (instantané).
def _maintenant_utc() -> datetime:
    """Horodatage UTC « naïf » (compatible SQLite et PostgreSQL)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class EnseignantTaux(Base):
    """Barème horaire d'un enseignant (FCFA par heure de cours donnée)."""

    __tablename__ = "enseignant_taux"
    __table_args__ = (
        ForeignKeyConstraint(
            ["school_id", "enseignant_id"],
            ["enseignants.school_id", "enseignants.id"],
        ),
        PrimaryKeyConstraint("school_id", "enseignant_id", name="pk_taux_ens"),
    )

    school_id: Mapped[int] = mapped_column(
        ForeignKey("ecole.id"), primary_key=True
    )
    enseignant_id: Mapped[str] = mapped_column(String(6), primary_key=True)
    taux_horaire: Mapped[int] = mapped_column(Integer, default=0)
    maj_le: Mapped[datetime] = mapped_column(
        DateTime, default=_maintenant_utc, onupdate=_maintenant_utc
    )


class Seance(Base):
    """Signature d'une séance de cours réellement donnée (cahier numérique).

    Une ligne = une entrée du cahier : date, classe, matière, horaires.
    L'horodatage ``cree_le`` fait office de signature horodatée.
    """

    __tablename__ = "seances"
    __table_args__ = (
        ForeignKeyConstraint(
            ["school_id", "enseignant_id"],
            ["enseignants.school_id", "enseignants.id"],
        ),
        ForeignKeyConstraint(
            ["school_id", "classe_id"],
            ["classes.school_id", "classes.id"],
        ),
        ForeignKeyConstraint(
            ["school_id", "matiere_id"],
            ["matieres.school_id", "matieres.id"],
        ),
        UniqueConstraint(
            "school_id", "enseignant_id", "date", "classe_id", "heure_debut",
            name="uq_seance_ens_classe_debut",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    school_id: Mapped[int] = mapped_column(
        ForeignKey("ecole.id"), nullable=False, default=1
    )
    enseignant_id: Mapped[str] = mapped_column(String(6))
    date: Mapped[date] = mapped_column(Date)
    classe_id: Mapped[str] = mapped_column(String(6))
    matiere_id: Mapped[str | None] = mapped_column(String(6), nullable=True)
    heure_debut: Mapped[str] = mapped_column(String(5))     # "08:00"
    heure_fin: Mapped[str] = mapped_column(String(5))       # "10:00"
    cree_le: Mapped[datetime] = mapped_column(DateTime, default=_maintenant_utc)


class FichePaie(Base):
    """Fiche de paie mensuelle d'un enseignant (générée par la direction)."""

    __tablename__ = "fiches_paie"
    __table_args__ = (
        ForeignKeyConstraint(
            ["school_id", "enseignant_id"],
            ["enseignants.school_id", "enseignants.id"],
        ),
        UniqueConstraint(
            "school_id", "enseignant_id", "mois",
            name="uq_fiche_ens_mois",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    school_id: Mapped[int] = mapped_column(
        ForeignKey("ecole.id"), nullable=False, default=1
    )
    enseignant_id: Mapped[str] = mapped_column(String(6))
    mois: Mapped[str] = mapped_column(String(7))            # "2026-09"
    heures: Mapped[float] = mapped_column(Float, default=0.0)
    taux_horaire: Mapped[int] = mapped_column(Integer, default=0)
    brut: Mapped[int] = mapped_column(Integer, default=0)   # FCFA
    statut: Mapped[str] = mapped_column(String(12), default="en_attente")
    cree_le: Mapped[datetime] = mapped_column(DateTime, default=_maintenant_utc)
    payee_le: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
