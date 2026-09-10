"""Envoi d'emails transactionnels (codes de vérification).

Deux fournisseurs pris en charge, au choix via la configuration :
- **Resend**  : ``RESEND_API_KEY`` (API HTTP, https://resend.com) ;
- **SMTP**    : ``SMTP_HOST`` / ``SMTP_PORT`` / ``SMTP_USER`` / ``SMTP_PASS``
  (ex. Gmail : smtp.gmail.com:587 + mot de passe d'application).

Uniquement la bibliothèque standard est utilisée (smtplib + urllib) : aucun
paquet supplémentaire n'est nécessaire côté Vercel.
"""

from __future__ import annotations

import json
import secrets
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from urllib import error as url_error
from urllib import request as url_request

from app.config import settings


class EmailNonConfigure(Exception):
    """Aucun fournisseur d'email n'est configuré."""


def generer_code(longueur: int | None = None) -> str:
    """Génère un code numérique aléatoire (cryptographiquement sûr)."""
    n = longueur or settings.code_longueur
    if n < 1:
        n = 6
    return f"{secrets.randbelow(10 ** n):0{n}d}"


def _adresse_expediteur() -> tuple[str | None, str]:
    """Décompose EMAIL_FROM : « Nom <email> » ou simple « email »."""
    brut = (settings.email_from or "").strip()
    if not brut:
        return None, ""
    if "<" in brut and ">" in brut:
        nom = brut[: brut.index("<")].strip()
        adr = brut[brut.index("<") + 1 : brut.index(">")].strip()
        return (nom or None), adr
    return None, brut


def _sujet_et_corps(code: str) -> tuple[str, str, str]:
    minutes = settings.code_expire_minutes
    sujet = f"Votre code SchoolManager : {code}"
    corps_texte = (
        f"Bonjour,\n\n"
        f"Voici votre code de connexion SchoolManager : {code}\n\n"
        f"Ce code est valable {minutes} minutes et ne doit être partagé avec "
        f"personne.\n\n"
        f"Si vous n'êtes pas à l'origine de cette demande, ignorez cet email."
    )
    corps_html = f"""\
<div style="font-family:Arial,Helvetica,sans-serif;max-width:520px;margin:auto">
  <h2 style="color:#1e3a8a;margin:0 0 12px">SchoolManager</h2>
  <p style="color:#333;font-size:15px">Bonjour,</p>
  <p style="color:#333;font-size:15px">Voici votre code de connexion :</p>
  <p style="font-size:34px;font-weight:bold;letter-spacing:8px;color:#1e3a8a;
     background:#eef2ff;border-radius:8px;padding:14px;text-align:center">
    {code}
  </p>
  <p style="color:#555;font-size:13px">
    Ce code est valable <strong>{minutes} minutes</strong> et ne doit être
    partagé avec personne.
  </p>
  <p style="color:#999;font-size:12px;margin-top:24px">
    Si vous n'êtes pas à l'origine de cette demande, ignorez simplement cet
    email.
  </p>
</div>"""
    return sujet, corps_texte, corps_html


def _expedier(destinataire: str, message: MIMEMultipart, corps_html: str) -> None:
    """Choisit le fournisseur configuré et expédie le message."""
    _nom, adr = _adresse_expediteur()
    if settings.resend_api_key:
        _envoyer_resend(adr, destinataire, message["Subject"], corps_html)
    elif settings.smtp_host and settings.smtp_user and settings.smtp_pass:
        _envoyer_smtp(adr, destinataire, message)
    else:
        raise EmailNonConfigure(
            "Aucun service d'envoi configuré (RESEND_API_KEY ou SMTP)."
        )


def _assembler(destinataire: str, sujet: str, texte: str, html: str) -> MIMEMultipart:
    """Construit un message multipart alternative prêt à envoyer."""
    nom, adr = _adresse_expediteur()
    message = MIMEMultipart("alternative")
    message["Subject"] = sujet
    message["From"] = formataddr((nom, adr)) if nom else adr
    message["To"] = destinataire
    message.attach(MIMEText(texte, "plain", "utf-8"))
    message.attach(MIMEText(html, "html", "utf-8"))
    return message


def envoyer_email_code(destinataire: str, code: str) -> None:
    """Envoie le code de vérification à l'adresse indiquée.

    Lève EmailNonConfigure si aucun fournisseur n'est prêt, ou une erreur
    réseau/SMTP en cas d'échec d'envoi.
    """
    _nom, adr = _adresse_expediteur()
    if not adr:
        raise EmailNonConfigure("Aucun expéditeur configuré (EMAIL_FROM).")

    sujet, corps_texte, corps_html = _sujet_et_corps(code)
    message = _assembler(destinataire, sujet, corps_texte, corps_html)
    _expedier(destinataire, message, corps_html)


def envoyer_invitation(
    destinataire: str, code: str, ecole: str, role: str
) -> None:
    """Invite une adresse email à rejoindre un établissement (Phase 3).

    Même mécanisme que le code de connexion (code à 6 chiffres, usage unique),
    mais le message précise l'école et le rôle proposés.
    """
    nom, adr = _adresse_expediteur()
    if not adr:
        raise EmailNonConfigure("Aucun expéditeur configuré (EMAIL_FROM).")

    minutes = settings.code_expire_minutes
    sujet = f"Invitation à rejoindre {ecole} — SchoolManager"
    corps_texte = (
        f"Bonjour,\n\n"
        f"{ecole} vous invite à rejoindre son espace SchoolManager avec le "
        f"rôle « {role} ».\n\n"
        f"Votre code d'invitation : {code}\n\n"
        f"Ce code est valable {minutes} minutes. Saisissez-le sur la page de "
        f"connexion, puis choisissez « Valider mon invitation ».\n\n"
        f"Si vous n'êtes pas concerné, ignorez cet email."
    )
    corps_html = f"""\
<div style="font-family:Arial,Helvetica,sans-serif;max-width:520px;margin:auto">
  <h2 style="color:#1e3a8a;margin:0 0 12px">SchoolManager</h2>
  <p style="color:#333;font-size:15px">Bonjour,</p>
  <p style="color:#333;font-size:15px">
    <strong>{ecole}</strong> vous invite à rejoindre son espace avec le rôle
    <strong>{role}</strong>.
  </p>
  <p style="color:#333;font-size:15px">Votre code d'invitation :</p>
  <p style="font-size:34px;font-weight:bold;letter-spacing:8px;color:#1e3a8a;
     background:#eef2ff;border-radius:8px;padding:14px;text-align:center">
    {code}
  </p>
  <p style="color:#555;font-size:13px">
    Ce code est valable <strong>{minutes} minutes</strong> et ne doit être
    partagé avec personne.
  </p>
  <p style="color:#999;font-size:12px;margin-top:24px">
    Si vous n'êtes pas concerné par cette invitation, ignorez cet email.
  </p>
</div>"""
    message = _assembler(destinataire, sujet, corps_texte, corps_html)
    _expedier(destinataire, message, corps_html)


def _envoyer_resend(expediteur: str, destinataire: str, sujet: str, html: str) -> None:
    """Envoi via l'API HTTP Resend (https://api.resend.com/emails)."""
    corps = json.dumps(
        {
            "from": expediteur,
            "to": [destinataire],
            "subject": sujet,
            "html": html,
        }
    ).encode("utf-8")
    req = url_request.Request(
        "https://api.resend.com/emails",
        data=corps,
        headers={
            "Authorization": f"Bearer {settings.resend_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with url_request.urlopen(req, timeout=20) as rep:
            if rep.status >= 300:
                raise EmailNonConfigure(f"Resend a répondu {rep.status}.")
    except url_error.HTTPError as e:
        raise RuntimeError(f"Resend a refusé l'envoi ({e.code}).") from e
    except url_error.URLError as e:
        raise RuntimeError("Resend injoignable.") from e


def _envoyer_smtp(expediteur: str, destinataire: str, message: MIMEMultipart) -> None:
    """Envoi via un relais SMTP (STARTTLS sur 587, ou SSL direct sur 465)."""
    hote = settings.smtp_host
    port = settings.smtp_port or 587
    try:
        if port == 465:
            serveur = smtplib.SMTP_SSL(hote, port, timeout=25)
        else:
            serveur = smtplib.SMTP(hote, port, timeout=25)
        with serveur:
            serveur.ehlo()
            if port != 465:
                serveur.starttls(context=ssl.create_default_context())
                serveur.ehlo()
            serveur.login(settings.smtp_user, settings.smtp_pass)
            serveur.sendmail(expediteur, [destinataire], message.as_string())
    except smtplib.SMTPAuthenticationError as e:
        raise RuntimeError(
            "Authentification SMTP refusée (vérifiez le mot de passe "
            "d'application)."
        ) from e
    except smtplib.SMTPException as e:
        raise RuntimeError("Échec de l'envoi SMTP.") from e
    except OSError as e:
        raise RuntimeError("Serveur SMTP injoignable.") from e
