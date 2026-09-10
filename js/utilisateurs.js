/* ============================================================
   SchoolManager — Utilisateurs (rattachement, Phase 3)
   ------------------------------------------------------------
   Un compte (`users`) = une identité (email + mot de passe).
   Un rattachement (`membres`) = le rôle de cette identité DANS
   l'établissement courant, avec un statut :

     actif    → accès normal à l'établissement
     invite   → invitation envoyée, code pas encore validé
     suspendu → accès coupé (réactivable)

   La même personne peut donc être Professeur dans une école et
   Parent dans une autre : cette page ne montre QUE l'école du
   jeton (l'API cloisonne, un identifiant d'une autre école
   répond 404).

   Routes appelées (backend/app/routers/membres.py) :
     GET    /membres                     liste des rattachements
     GET    /membres/invitations         invitations en attente
     POST   /membres                     inviter une adresse
     POST   /membres/{id}/invitation     renvoyer un code
     PUT    /membres/{id}/role           changer le rôle
     PUT    /membres/{id}/statut         suspendre / réactiver
     DELETE /membres/{id}                retirer de l'établissement
     DELETE /membres/invitations/{id}    annuler une invitation
     GET    /auth/options                service email actif ?
   ============================================================ */

(function () {
  "use strict";

  var SM = window.SM;

  function el(id) { return document.getElementById(id); }

  var ROLES_LIBELLES = {
    Administrateur: "🛡️ Administrateur",
    Professeur: "👨‍🏫 Professeur",
    Surveillant: "📋 Surveillant",
    Élève: "👨‍🎓 Élève",
    Parent: "👨‍👩‍👧 Parent"
  };

  var STATUTS = {
    actif: { libelle: "Actif", classe: "badge-success" },
    invite: { libelle: "Invitation en attente", classe: "badge-warning" },
    suspendu: { libelle: "Suspendu", classe: "badge-danger" }
  };

  /* ---------- Garde : page réservée à la direction ---------- */
  var session = SM.getSession();
  if (!session || session.role !== "Administrateur") {
    if (window.API) window.API.deconnexion();
    try { sessionStorage.removeItem("sm_session"); } catch (e) { /* ignore */ }
    window.location.replace("dashboard.html");
    return;
  }

  /* ---------- État ---------- */
  var etat = {
    membres: [],
    invitations: [],
    rolesValides: ["Administrateur", "Professeur", "Surveillant", "Élève", "Parent"],
    emailActif: true
  };
  var filtre = "";
  var membreCourant = null;    // rattachement ciblé par la modale rôle / retrait
  var invitationCourante = null;

  function escape(s) { return SM.escapeHtml(s); }

  /* ---------- Compteurs ---------- */
  function rendreCompteurs() {
    var zone = el("miniCounts");
    if (!zone) return;
    var actifs = etat.membres.filter(function (m) { return m.statut === "actif"; }).length;
    var invites = etat.membres.filter(function (m) { return m.statut === "invite"; }).length
      + etat.invitations.filter(function (i) { return i.statut === "invite"; }).length;
    var suspendus = etat.membres.filter(function (m) { return m.statut === "suspendu"; }).length;
    zone.innerHTML =
      '<div class="mini-stat"><div class="v">' + etat.membres.length + '</div><div class="l">Rattachés</div></div>' +
      '<div class="mini-stat"><div class="v">' + actifs + '</div><div class="l">Actifs</div></div>' +
      '<div class="mini-stat"><div class="v">' + invites + '</div><div class="l">Invitations</div></div>' +
      '<div class="mini-stat"><div class="v">' + suspendus + '</div><div class="l">Suspendus</div></div>';
  }

  /* ---------- Rendu du tableau des membres ---------- */
  function badgeStatutMembre(statut) {
    var s = STATUTS[statut] || { libelle: statut, classe: "badge-neutral" };
    return '<span class="badge ' + s.classe + '">' + escape(s.libelle) + "</span>";
  }

  function badgeRole(role) {
    return SM.badgeStatut(role);
  }

  function dateCourte(iso) {
    if (!iso) return "—";
    var d = new Date(iso);
    if (isNaN(d.getTime())) return "—";
    return d.toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" });
  }

  function rendreMembres() {
    var tbody = el("tableBody");
    if (!tbody) return;
    var liste = etat.membres.filter(function (m) {
      if (!filtre) return true;
      return (m.nom + " " + m.email).toLowerCase().indexOf(filtre) !== -1;
    });

    if (!liste.length) {
      var message = etat.membres.length
        ? "Aucun membre ne correspond à « " + escape(filtre) + " »."
        : "Invitez la première personne à rejoindre l'établissement.";
      tbody.innerHTML =
        '<tr><td colspan="6"><div class="empty-state"><div class="e-ico">👥</div>' +
        "<h4>Aucun utilisateur à afficher</h4><p>" + message + "</p></div></td></tr>";
      el("countLabel").textContent = "0 utilisateur";
      return;
    }

    tbody.innerHTML = liste.map(function (m) {
      var actions =
        '<div class="row-actions" style="justify-content:center">' +
        (m.statut === "invite"
          ? '<button type="button" class="btn-icon primary-h" title="Renvoyer l\'invitation" data-renvoyer="' + m.id + '">✉️</button>'
          : "") +
        '<button type="button" class="btn-icon primary-h" title="Changer le rôle" data-role="' + m.id + '">🔁</button>' +
        (m.statut === "suspendu"
          ? '<button type="button" class="btn-icon primary-h" title="Réactiver l\'accès" data-reactiv="' + m.id + '">▶️</button>'
          : '<button type="button" class="btn-icon danger" title="Suspendre l\'accès" data-suspend="' + m.id + '">⏸️</button>') +
        '<button type="button" class="btn-icon danger" title="Retirer de l\'établissement" data-retirer="' + m.id + '">🗑️</button>' +
        "</div>";
      var liens =
        (m.enseignant_id ? ' <span class="text-xs text-muted">fiche ' + escape(m.enseignant_id) + "</span>" : "") +
        (m.eleve_id ? ' <span class="text-xs text-muted">élève ' + escape(m.eleve_id) + "</span>" : "");
      return (
        "<tr>" +
        "  <td><div class='cell-user'>" + SM.avatarHTML(m.nom, "sm") +
        "    <div><div class='fw-600'>" + escape(m.nom) + "</div>" +
        "    <div class='text-xs text-muted'>" + (m.actif ? "Compte plateforme actif" : "Compte plateforme désactivé") + liens + "</div></div>" +
        "  </div></td>" +
        '  <td class="text-sm">' + escape(m.email) + "</td>" +
        "  <td>" + badgeRole(m.role) + "</td>" +
        "  <td>" + badgeStatutMembre(m.statut) + "</td>" +
        '  <td class="text-sm text-muted">' + dateCourte(m.cree_le) + "</td>" +
        "  <td>" + actions + "</td>" +
        "</tr>"
      );
    }).join("");

    el("countLabel").textContent =
      liste.length + (liste.length > 1 ? " utilisateurs" : " utilisateur") +
      (liste.length !== etat.membres.length ? " sur " + etat.membres.length : "");
  }

  /* ---------- Rendu des invitations en attente ---------- */
  function duree(secondes) {
    if (secondes === null || secondes === undefined) return "—";
    if (secondes <= 0) return "expiré";
    if (secondes < 60) return secondes + " s";
    var minutes = Math.floor(secondes / 60);
    var reste = secondes % 60;
    return minutes + " min" + (reste ? " " + reste + " s" : "");
  }

  function rendreInvitations() {
    var carte = el("carteInvitations");
    var tbody = el("invitationsBody");
    if (!carte || !tbody) return;
    if (!etat.invitations.length) {
      carte.style.display = "none";
      tbody.innerHTML = "";
      return;
    }
    carte.style.display = "";
    tbody.innerHTML = etat.invitations.map(function (i) {
      var expiree = i.statut === "expire";
      return (
        "<tr>" +
        '  <td class="fw-600">' + escape(i.email) + "</td>" +
        "  <td>" + badgeRole(i.role) + "</td>" +
        '  <td class="text-sm">' + (expiree ? "—" : duree(i.expire_dans)) + "</td>" +
        "  <td>" + (expiree
          ? '<span class="badge badge-neutral">Expirée</span>'
          : '<span class="badge badge-warning">En attente</span>') + "</td>" +
        '  <td><div class="row-actions" style="justify-content:center">' +
        '    <button type="button" class="btn-icon primary-h" title="Renvoyer le code" data-inv-renvoyer="' + i.id + '">✉️</button>' +
        '    <button type="button" class="btn-icon danger" title="Annuler l\'invitation" data-inv-annuler="' + i.id + '">🗑️</button>' +
        "  </div></td>" +
        "</tr>"
      );
    }).join("");
  }

  /* ---------- Chargement ---------- */
  function messageErreur(err, defaut) {
    if (err && err.reseau) return "Serveur injoignable : vérifiez que le backend est démarré.";
    if (err && err.detail) return err.detail;
    return defaut;
  }

  function charger(emailConfigure) {
    if (!window.API || !window.API.membres) return;
    var zone = el("tableBody");
    if (zone) zone.innerHTML = '<tr><td colspan="6" class="text-sm text-muted">Chargement…</td></tr>';

    var taches = [window.API.membres(), window.API.invitationsMembres()];
    if (emailConfigure) taches.push(window.API.optionsAuth());

    return Promise.all(taches).then(function (resultats) {
      etat.membres = resultats[0] || [];
      etat.invitations = resultats[1] || [];
      var options = resultats[2];
      if (options) etat.emailActif = !!options.code_email;
      var alerte = el("alerteEmail");
      if (alerte) alerte.style.display = etat.emailActif ? "none" : "";
      rendreCompteurs();
      rendreMembres();
      rendreInvitations();
    }).catch(function (err) {
      if (zone) {
        zone.innerHTML =
          '<tr><td colspan="6"><div class="empty-state"><div class="e-ico">⚠️</div>' +
          "<h4>Chargement impossible</h4><p>" +
          escape(messageErreur(err, "Erreur serveur.")) + "</p></div></td></tr>";
      }
      SM.toast(messageErreur(err, "Chargement des utilisateurs impossible."), "error");
    });
  }

  function recharger() { return charger(false); }

  /* ---------- Recherche ---------- */
  var champRecherche = el("searchInput");
  if (champRecherche) {
    champRecherche.addEventListener("input", function () {
      filtre = champRecherche.value.trim().toLowerCase();
      rendreMembres();
    });
  }

  /* ---------- Inviter ---------- */
  var btnInviter = el("btnInviter");
  if (btnInviter) {
    btnInviter.addEventListener("click", function () {
      var email = el("invEmail").value.trim();
      var role = el("invRole").value;
      var errInv = el("errInvitation");
      var errEmail = el("errInvEmail");
      errInv.classList.remove("show");
      errEmail.classList.remove("show");
      el("invEmail").classList.remove("invalid");

      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
        el("invEmail").classList.add("invalid");
        errEmail.classList.add("show");
        return;
      }

      btnInviter.disabled = true;
      btnInviter.textContent = "Envoi…";
      window.API.inviterMembre({ email: email, role: role })
        .then(function (rep) {
          btnInviter.disabled = false;
          btnInviter.textContent = "✉️ Envoyer l'invitation";
          SM.closeModal("modalInviter");
          el("invEmail").value = "";
          SM.toast("Invitation envoyée à " + email + " ✅", "success");
          return charger(false).then(function () {
            if (rep && rep.message) SM.toast(rep.message);
          });
        })
        .catch(function (err) {
          btnInviter.disabled = false;
          btnInviter.textContent = "✉️ Envoyer l'invitation";
          errInv.textContent = messageErreur(err, "Envoi de l'invitation impossible.");
          errInv.classList.add("show");
        });
    });
  }

  /* ---------- Actions du tableau des membres ---------- */
  var tbody = el("tableBody");
  if (tbody) {
    tbody.addEventListener("click", function (ev) {
      var btn = ev.target.closest("button[data-renvoyer], button[data-role], button[data-suspend], button[data-reactiv], button[data-retirer]");
      if (!btn) return;
      var id = parseInt(
        btn.getAttribute("data-renvoyer") || btn.getAttribute("data-role") ||
        btn.getAttribute("data-suspend") || btn.getAttribute("data-reactiv") ||
        btn.getAttribute("data-retirer"), 10);
      var membre = etat.membres.filter(function (m) { return m.id === id; })[0];

      if (btn.hasAttribute("data-renvoyer")) { renvoyerCode(btn, id); return; }
      if (btn.hasAttribute("data-suspend")) { changerStatut(btn, id, "suspendu"); return; }
      if (btn.hasAttribute("data-reactiv")) { changerStatut(btn, id, "actif"); return; }
      if (!membre) return;
      if (btn.hasAttribute("data-role")) { ouvrirRole(membre); return; }
      ouvrirRetrait(membre);
    });
  }

  function renvoyerCode(btn, id) {
    btn.disabled = true;
    window.API.renvoyerInvitation(id).then(function () {
      SM.toast("Nouveau code envoyé ✅", "success");
      recharger();
    }).catch(function (err) {
      btn.disabled = false;
      SM.toast(messageErreur(err, "Renvoi impossible."), "error");
    });
  }

  function changerStatut(btn, id, statut) {
    btn.disabled = true;
    window.API.changerStatutMembre(id, statut).then(function () {
      SM.toast(statut === "suspendu" ? "Accès suspendu." : "Accès réactivé ✅",
        statut === "suspendu" ? "warning" : "success");
      recharger();
    }).catch(function (err) {
      btn.disabled = false;
      SM.toast(messageErreur(err, "Modification impossible."), "error");
    });
  }

  /* ---------- Modale rôle ---------- */
  function ouvrirRole(membre) {
    membreCourant = membre;
    el("roleResume").innerHTML = "<b>" + escape(membre.nom) + "</b> — " + escape(membre.email) +
      "<br>Rôle actuel : " + escape(membre.role);
    el("roleSelect").value = membre.role;
    el("errRole").classList.remove("show");
    SM.openModal("modalRole");
  }

  var btnSaveRole = el("btnSaveRole");
  if (btnSaveRole) {
    btnSaveRole.addEventListener("click", function () {
      if (!membreCourant) return;
      var role = el("roleSelect").value;
      if (role === membreCourant.role) { SM.closeModal("modalRole"); return; }
      btnSaveRole.disabled = true;
      btnSaveRole.textContent = "Enregistrement…";
      window.API.changerRoleMembre(membreCourant.id, role).then(function () {
        btnSaveRole.disabled = false;
        btnSaveRole.textContent = "💾 Enregistrer";
        SM.closeModal("modalRole");
        SM.toast("Rôle mis à jour : " + role + " ✅", "success");
        recharger();
      }).catch(function (err) {
        btnSaveRole.disabled = false;
        btnSaveRole.textContent = "💾 Enregistrer";
        el("errRole").textContent = messageErreur(err, "Changement de rôle impossible.");
        el("errRole").classList.add("show");
      });
    });
  }

  /* ---------- Modale retrait ---------- */
  function ouvrirRetrait(membre) {
    membreCourant = membre;
    el("retirerResume").innerHTML = "Retirer <b>" + escape(membre.nom) + "</b> (" + escape(membre.email) +
      ") de l'établissement ?";
    el("errRetirer").classList.remove("show");
    SM.openModal("modalRetirer");
  }

  var btnConfirmRetirer = el("btnConfirmRetirer");
  if (btnConfirmRetirer) {
    btnConfirmRetirer.addEventListener("click", function () {
      if (!membreCourant) return;
      btnConfirmRetirer.disabled = true;
      btnConfirmRetirer.textContent = "Retrait…";
      window.API.retirerMembre(membreCourant.id).then(function () {
        btnConfirmRetirer.disabled = false;
        btnConfirmRetirer.textContent = "Retirer";
        SM.closeModal("modalRetirer");
        SM.toast("Membre retiré de l'établissement.", "success");
        recharger();
      }).catch(function (err) {
        btnConfirmRetirer.disabled = false;
        btnConfirmRetirer.textContent = "Retirer";
        // Cas le plus fréquent : dernier établissement du compte → suspendre.
        el("errRetirer").textContent = messageErreur(err, "Retrait impossible.");
        el("errRetirer").classList.add("show");
      });
    });
  }

  /* ---------- Actions du tableau des invitations ---------- */
  var invitationsBody = el("invitationsBody");
  if (invitationsBody) {
    invitationsBody.addEventListener("click", function (ev) {
      var btn = ev.target.closest("button[data-inv-renvoyer], button[data-inv-annuler]");
      if (!btn) return;
      var id = parseInt(btn.getAttribute("data-inv-renvoyer") || btn.getAttribute("data-inv-annuler"), 10);
      var invitation = etat.invitations.filter(function (i) { return i.id === id; })[0];
      if (!invitation) return;

      if (btn.hasAttribute("data-inv-renvoyer")) {
        btn.disabled = true;
        // Renvoyer = réinviter la même adresse (nouveau code, anti-spam 60 s).
        window.API.inviterMembre({ email: invitation.email, role: invitation.role })
          .then(function () {
            SM.toast("Nouveau code envoyé à " + invitation.email + " ✅", "success");
            recharger();
          })
          .catch(function (err) {
            btn.disabled = false;
            SM.toast(messageErreur(err, "Renvoi impossible."), "error");
          });
        return;
      }

      invitationCourante = invitation;
      if (!window.confirm("Annuler l'invitation de " + invitation.email + " ?")) return;
      btn.disabled = true;
      window.API.reverInvitation(id).then(function () {
        SM.toast("Invitation annulée.", "success");
        recharger();
      }).catch(function (err) {
        btn.disabled = false;
        SM.toast(messageErreur(err, "Annulation impossible."), "error");
      });
    });
  }

  /* ---------- Démarrage ---------- */
  charger(true);
})();
