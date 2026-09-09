"""Modèles SQLAlchemy — miroir relationnel de `js/data.js` (window.SD).

Conventions de parité avec le front :
- `classes.id`, `matieres.id`, `enseignants.id`, `eleves.id`, `annonces.id`
  conservent les codes métier exacts ("3A", "S1", "T001", "EL001", "A1"…).
- `notes`, `presences`, `paiements`, `versements`, `parents`, `users`
  utilisent des identifiants entiers auto-générés.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
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
    Column("classe_id", ForeignKey("classes.id"), primary_key=True),
    Column("matiere_id", ForeignKey("matieres.id"), primary_key=True),
    Column("ordre", Integer, default=0),  # ordre d'affichage
)

enseignant_classe = Table(
    "enseignant_classe",
    Base.metadata,
    Column("enseignant_id", ForeignKey("enseignants.id"), primary_key=True),
    Column("classe_id", ForeignKey("classes.id"), primary_key=True),
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
# Matières
# ---------------------------------------------------------------
class Matiere(Base):
    __tablename__ = "matieres"

    id: Mapped[str] = mapped_column(String(6), primary_key=True)   # "S1"…
    nom: Mapped[str] = mapped_column(String(60))
    coef: Mapped[int] = mapped_column(Integer)
    icone: Mapped[str] = mapped_column(String(6))
    couleur: Mapped[str] = mapped_column(String(20))

    enseignants: Mapped[list["Enseignant"]] = relationship(back_populates="matiere")
    classes: Mapped[list["Classe"]] = relationship(
        secondary=classe_matiere, back_populates="matieres"
    )


# ---------------------------------------------------------------
# Classes
# ---------------------------------------------------------------
class Classe(Base):
    __tablename__ = "classes"

    id: Mapped[str] = mapped_column(String(6), primary_key=True)   # "6A", "3B"…
    nom: Mapped[str] = mapped_column(String(20))
    cycle: Mapped[str] = mapped_column(String(10))                  # Collège / Lycée
    salle: Mapped[str] = mapped_column(String(20))
    principal_id: Mapped[str | None] = mapped_column(
        ForeignKey("enseignants.id"), nullable=True
    )

    principal: Mapped["Enseignant | None"] = relationship(
        foreign_keys=[principal_id], back_populates="classes_principales"
    )
    eleves: Mapped[list["Eleve"]] = relationship(back_populates="classe")
    matieres: Mapped[list[Matiere]] = relationship(
        secondary=classe_matiere, back_populates="classes", order_by=classe_matiere.c.ordre
    )
    enseignants: Mapped[list["Enseignant"]] = relationship(
        secondary=enseignant_classe, back_populates="classes"
    )


# ---------------------------------------------------------------
# Enseignants
# ---------------------------------------------------------------
class Enseignant(Base):
    __tablename__ = "enseignants"

    id: Mapped[str] = mapped_column(String(6), primary_key=True)    # "T001"…
    nom: Mapped[str] = mapped_column(String(40))
    prenom: Mapped[str] = mapped_column(String(40))
    sexe: Mapped[str] = mapped_column(String(1))
    tel: Mapped[str] = mapped_column(String(20))
    email: Mapped[str] = mapped_column(String(80))
    matiere_id: Mapped[str | None] = mapped_column(
        ForeignKey("matieres.id"), nullable=True
    )
    statut: Mapped[str] = mapped_column(String(10), default="Actif")

    matiere: Mapped[Matiere | None] = relationship(back_populates="enseignants")
    classes: Mapped[list[Classe]] = relationship(
        secondary=enseignant_classe, back_populates="enseignants"
    )
    classes_principales: Mapped[list[Classe]] = relationship(
        foreign_keys="Classe.principal_id", back_populates="principal"
    )


# ---------------------------------------------------------------
# Parents
# ---------------------------------------------------------------
class Parent(Base):
    __tablename__ = "parents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nom: Mapped[str] = mapped_column(String(80))
    lien: Mapped[str] = mapped_column(String(20))       # Père / Mère…
    tel: Mapped[str] = mapped_column(String(20))
    email: Mapped[str] = mapped_column(String(80))
    profession: Mapped[str] = mapped_column(String(40))
    adresse: Mapped[str] = mapped_column(String(80))

    enfants: Mapped[list["Eleve"]] = relationship(back_populates="parent")


# ---------------------------------------------------------------
# Élèves
# ---------------------------------------------------------------
class Eleve(Base):
    __tablename__ = "eleves"

    id: Mapped[str] = mapped_column(String(6), primary_key=True)    # "EL001"…
    nom: Mapped[str] = mapped_column(String(40))
    prenom: Mapped[str] = mapped_column(String(40))
    sexe: Mapped[str] = mapped_column(String(1))                    # M / F
    naissance: Mapped[date] = mapped_column(Date)
    classe_id: Mapped[str] = mapped_column(ForeignKey("classes.id"))
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
# Notes
# ---------------------------------------------------------------
class Note(Base):
    __tablename__ = "notes"
    __table_args__ = (
        UniqueConstraint("eleve_id", "matiere_id", "eval", name="uq_note_eleve_matiere_eval"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    eleve_id: Mapped[str] = mapped_column(ForeignKey("eleves.id"))
    matiere_id: Mapped[str] = mapped_column(ForeignKey("matieres.id"))
    eval: Mapped[str] = mapped_column(String(20))       # Devoir 1 / Devoir 2 / Composition
    note: Mapped[float] = mapped_column(Float)          # 0 → 20, pas de 0,5

    eleve: Mapped[Eleve] = relationship(back_populates="notes")
    matiere: Mapped[Matiere] = relationship()


# ---------------------------------------------------------------
# Présences
# ---------------------------------------------------------------
class Presence(Base):
    __tablename__ = "presences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    eleve_id: Mapped[str] = mapped_column(ForeignKey("eleves.id"))
    date: Mapped[date] = mapped_column(Date)
    statut: Mapped[str] = mapped_column(String(1))      # P / R / A

    eleve: Mapped[Eleve] = relationship(back_populates="presences")


# ---------------------------------------------------------------
# Paiements (dossier) + Versements
# ---------------------------------------------------------------
class Paiement(Base):
    __tablename__ = "paiements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    eleve_id: Mapped[str] = mapped_column(ForeignKey("eleves.id"))
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
    paiement_id: Mapped[int] = mapped_column(ForeignKey("paiements.id"))
    montant: Mapped[int] = mapped_column(Integer)
    date: Mapped[date] = mapped_column(Date)
    mode: Mapped[str] = mapped_column(String(20))       # Espèces / Mobile Money / Chèque

    paiement: Mapped[Paiement] = relationship(back_populates="versements")


# ---------------------------------------------------------------
# Annonces
# ---------------------------------------------------------------
class Annonce(Base):
    __tablename__ = "annonces"

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
    # Liaisons optionnelles vers la personne physique
    eleve_id: Mapped[str | None] = mapped_column(
        ForeignKey("eleves.id"), nullable=True
    )
    enseignant_id: Mapped[str | None] = mapped_column(
        ForeignKey("enseignants.id"), nullable=True
    )
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("parents.id"), nullable=True
    )


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

    enseignant_id: Mapped[str] = mapped_column(
        ForeignKey("enseignants.id"), primary_key=True
    )
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
        UniqueConstraint(
            "enseignant_id", "date", "classe_id", "heure_debut",
            name="uq_seance_ens_classe_debut",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    enseignant_id: Mapped[str] = mapped_column(ForeignKey("enseignants.id"))
    date: Mapped[date] = mapped_column(Date)
    classe_id: Mapped[str] = mapped_column(ForeignKey("classes.id"))
    matiere_id: Mapped[str | None] = mapped_column(
        ForeignKey("matieres.id"), nullable=True
    )
    heure_debut: Mapped[str] = mapped_column(String(5))     # "08:00"
    heure_fin: Mapped[str] = mapped_column(String(5))       # "10:00"
    cree_le: Mapped[datetime] = mapped_column(DateTime, default=_maintenant_utc)


class FichePaie(Base):
    """Fiche de paie mensuelle d'un enseignant (générée par la direction)."""

    __tablename__ = "fiches_paie"
    __table_args__ = (
        UniqueConstraint("enseignant_id", "mois", name="uq_fiche_ens_mois"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    enseignant_id: Mapped[str] = mapped_column(ForeignKey("enseignants.id"))
    mois: Mapped[str] = mapped_column(String(7))            # "2026-09"
    heures: Mapped[float] = mapped_column(Float, default=0.0)
    taux_horaire: Mapped[int] = mapped_column(Integer, default=0)
    brut: Mapped[int] = mapped_column(Integer, default=0)   # FCFA
    statut: Mapped[str] = mapped_column(String(12), default="en_attente")
    cree_le: Mapped[datetime] = mapped_column(DateTime, default=_maintenant_utc)
    payee_le: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
