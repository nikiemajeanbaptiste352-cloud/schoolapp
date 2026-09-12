/* ============================================================
   SchoolManager — Paramètres
   ============================================================ */

(function () {
  "use strict";

  var SM = window.SM;
  var SD = window.SD;

  function el(id) { return document.getElementById(id); }

  function lignes(rows) {
    return rows.map(function (r) {
      return '<div class="settings-row"><div><div class="s-k">' + r[0] + "</div>" +
        (r[2] ? '<div class="s-d">' + r[2] + "</div>" : "") + "</div>" +
        '<div class="fw-600" style="text-align:right">' + r[1] + "</div></div>";
    }).join("");
  }

  /* ---------- Établissement ---------- */
  function rendreEcole() {
    var e = SD.ecole || {};
    el("ecoleRows").innerHTML = lignes([
      ["Nom", SM.escapeHtml(e.nom || "—")],
      ["Sigle", SM.escapeHtml(e.sigle || "—")],
      ["Slogan", SM.escapeHtml(e.slogan || "—")],
      ["Adresse", SM.escapeHtml(e.adresse || "—")],
      ["Téléphone", SM.escapeHtml(e.telephone || "—")],
      ["Email", SM.escapeHtml(e.email || "—")],
      ["Devise", SM.escapeHtml(e.devise || "FCFA")]
    ]);
  }
  function rendreAnnee() {
    var e = SD.ecole || {};
    el("anneeRows").innerHTML = lignes([
      ["Année scolaire", SM.escapeHtml(e.annee || "—")],
      ["Classes", SD.classes.length + " classes"],
      ["Élèves inscrits", SD.eleves.length + " élèves"],
      ["Enseignants", SD.enseignants.length + " professeurs"],
      ["Matières au programme", SD.matieres.length + " matières"],
      ["Évaluations", SD.EVALS.length + " par matière (" + SD.EVALS.join(", ") + ")"]
    ]);
  }
  rendreEcole();
  rendreAnnee();

  // Si l'école n'est pas encore configurée (base vide), on force le mode
  // « création » dans la modale (SD.ecole n'a alors pas de nom renseigné).
  var ecoleConfiguree = !!(SD.ecole && SD.ecole.nom);

  /* ---------- Session ---------- */
  // Identité : le serveur fait foi (`moi` + `capacites.role`), le stockage
  // local n'est qu'un repli d'affichage.
  var sess = SM.getSession() || {};
  var moi = window.SM_MOI || {};
  var roleCourant = SM.roleCourant() || sess.role || "";
  var roleLabel = { Administrateur: "🛡️ Administrateur", Professeur: "👨‍🏫 Professeur", Surveillant: "📋 Surveillant", Élève: "👨‍🎓 Élève", Parent: "👨‍👩‍👧 Parent" };
  el("sessionRows").innerHTML = lignes([
    ["Connecté en tant que", SM.escapeHtml(moi.nom || sess.nom || "—")],
    ["Adresse email", SM.escapeHtml(moi.email || sess.email || "—")],
    ["Rôle", roleLabel[roleCourant] || SM.escapeHtml(roleCourant || "—")]
  ]);

  /* ---------- Comptes utilisateurs (réservé admin) ---------- */
  function roleBadge(role) {
    var cls = "badge-neutral";
    if (role === "Administrateur") cls = "badge-danger";
    else if (role === "Professeur") cls = "badge-info";
    else if (role === "Parent") cls = "badge-success";
    return '<span class="badge ' + cls + '">' + SM.escapeHtml(role) + "</span>";
  }

  function afficherComptes(comptes) {
    var zone = el("comptesList");
    if (!zone) return;
    if (!comptes || !comptes.length) {
      zone.innerHTML = '<p class="text-sm text-muted">Aucun compte pour le moment.</p>';
      return;
    }
    var html = '<div class="card" style="border:1px solid var(--border);padding:6px 14px">';
    comptes.forEach(function (c) {
      var statut = c.actif
        ? '<span class="badge badge-success">Actif</span>'
        : '<span class="badge badge-warning">Désactivé</span>';
      html +=
        '<div class="settings-row">' +
        "<div>" +
        '<div class="s-k">' + SM.escapeHtml(c.nom) + "</div>" +
        '<div class="s-d">' + SM.escapeHtml(c.email) + "</div>" +
        "</div>" +
        '<div class="flex" style="gap:8px;align-items:center">' +
        roleBadge(c.role) + statut +
        "</div>" +
        "</div>";
    });
    html += "</div>";
    zone.innerHTML = html;
  }

  function chargerComptes() {
    if (!window.API || !window.API.comptes) return;
    window.API.comptes().then(function (liste) {
      afficherComptes(liste || []);
    }).catch(function () {
      var zone = el("comptesList");
      if (zone) zone.innerHTML = '<p class="text-sm" style="color:var(--danger-text)">Impossible de charger les comptes.</p>';
    });
  }

  if (SM.peut("membres.ecrire")) {
    var comptesCard = el("comptesCard");
    if (comptesCard) comptesCard.style.display = "";
    chargerComptes();
  }

  /* ---------- Création d'un compte (admin) ---------- */
  var formCompte = el("formCompte");
  if (formCompte) {
    var cpNom = el("cpNom");
    var cpEmail = el("cpEmail");
    var cpMdp = el("cpMdp");
    var errCpNom = el("errCpNom");
    var errCpEmail = el("errCpEmail");
    var errCpMdp = el("errCpMdp");
    var errCompte = el("errCompte");
    var btnCreerCompte = el("btnCreerCompte");

    function okCp(input, errEl) { input.classList.remove("invalid"); errEl.classList.remove("show"); }
    function badCp(input, errEl, msg) {
      input.classList.add("invalid");
      errEl.textContent = msg;
      errEl.classList.add("show");
    }

    cpNom.addEventListener("input", function () { okCp(cpNom, errCpNom); });
    cpEmail.addEventListener("input", function () { okCp(cpEmail, errCpEmail); });
    cpMdp.addEventListener("input", function () { okCp(cpMdp, errCpMdp); });

    formCompte.addEventListener("submit", function (e) {
      e.preventDefault();
      if (errCompte) { errCompte.classList.remove("show"); errCompte.textContent = ""; }
      var nom = cpNom.value.trim();
      var email = cpEmail.value.trim();
      var mdp = cpMdp.value.trim();
      var role = el("cpRole").value;
      var valide = true;

      if (!nom) { badCp(cpNom, errCpNom, "Veuillez saisir le nom complet."); valide = false; }
      else okCp(cpNom, errCpNom);

      if (!email) { badCp(cpEmail, errCpEmail, "Veuillez saisir une adresse email."); valide = false; }
      else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
        badCp(cpEmail, errCpEmail, "Format d'email invalide.");
        valide = false;
      } else okCp(cpEmail, errCpEmail);

      if (mdp.length < 6) { badCp(cpMdp, errCpMdp, "Le mot de passe doit contenir au moins 6 caractères."); valide = false; }
      else okCp(cpMdp, errCpMdp);

      if (!valide || !window.API || !window.API.creerCompte) return;

      btnCreerCompte.disabled = true;
      btnCreerCompte.textContent = "Création…";
      window.API.creerCompte({ nom: nom, email: email, password: mdp, role: role })
        .then(function (c) {
          btnCreerCompte.disabled = false;
          btnCreerCompte.textContent = "Créer le compte";
          SM.toast("Compte de " + (c.nom || nom) + " créé ✅", "success");
          formCompte.reset();
          chargerComptes();
        })
        .catch(function (err) {
          btnCreerCompte.disabled = false;
          btnCreerCompte.textContent = "Créer le compte";
          var msg = (err && err.detail) || "Création impossible.";
          if (errCompte) {
            errCompte.textContent = msg;
            errCompte.classList.add("show");
          } else {
            SM.toast(msg, "error");
          }
        });
    });
  }

  /* ---------- Modification de l'établissement (admin) ---------- */
  if (SM.peut("ecole.ecrire")) {
    var btnEditEcole = el("btnEditEcole");
    if (btnEditEcole) btnEditEcole.style.display = "";

    function clearErreursEcole() {
      document.querySelectorAll(".field-error.show").forEach(function (x) { x.classList.remove("show"); });
      document.querySelectorAll(".input.invalid").forEach(function (x) { x.classList.remove("invalid"); });
    }
    function ouvrirEcole() {
      var e = SD.ecole || {};
      el("ecoleModalTitle").textContent = ecoleConfiguree
        ? "✏️ Modifier l'établissement"
        : "🏫 Configurer l'établissement";
      el("ecNom").value = e.nom || "";
      el("ecSigle").value = e.sigle || "";
      el("ecDevise").value = e.devise || "FCFA";
      el("ecSlogan").value = e.slogan || "";
      el("ecTel").value = e.telephone || "";
      el("ecEmail").value = e.email || "";
      el("ecAdresse").value = e.adresse || "";
      el("ecAnnee").value = e.annee || "";
      el("ecVersion").value = e.version || "1.0.0";
      clearErreursEcole();
      SM.openModal("modalEcole");
    }
    if (btnEditEcole) btnEditEcole.addEventListener("click", ouvrirEcole);

    // Demande de création depuis le panneau « Établissement » quand la base
    // est vide (aucune école configurée) — bouton dédié affiché à la place.
    if (!ecoleConfiguree && btnEditEcole) {
      btnEditEcole.textContent = "➕ Configurer l'établissement";
    }

    el("btnSaveEcole").addEventListener("click", function () {
      clearErreursEcole();
      var nom = el("ecNom").value.trim();
      var ok = true;
      if (!nom) {
        el("ecNom").classList.add("invalid");
        el("errEcNom").classList.add("show");
        ok = false;
      }
      if (!ok) { SM.toast("Veuillez renseigner le nom de l'établissement.", "error"); return; }

      var corps = {
        nom: nom,
        sigle: el("ecSigle").value.trim(),
        devise: el("ecDevise").value.trim() || "FCFA",
        slogan: el("ecSlogan").value.trim(),
        telephone: el("ecTel").value.trim(),
        email: el("ecEmail").value.trim(),
        adresse: el("ecAdresse").value.trim(),
        annee: el("ecAnnee").value.trim(),
        version: el("ecVersion").value.trim() || "1.0.0"
      };
      var bouton = el("btnSaveEcole");
      bouton.disabled = true;
      bouton.textContent = "Enregistrement…";

      function terminer() { bouton.disabled = false; bouton.textContent = "💾 Enregistrer"; }
      function reussite(message) {
        SM.closeModal("modalEcole");
        SM.toast(message, "success");
        ecoleConfiguree = true;
        rendreEcole();
        rendreAnnee();
      }
      function echec(err) {
        SM.toast("Enregistrement impossible : " + (err && err.detail ? err.detail : "erreur réseau."), "error");
        terminer();
      }

      // Base vide → création (POST /ecole) ; sinon mise à jour (PUT /ecole).
      var requeteEcole = ecoleConfiguree ? window.API.majEcole(corps) : window.API.creerEcole(corps);
      requeteEcole.then(function (rep) {
        // Mise à jour sur place de SD.ecole (objet vivant partagé)
        ["nom", "sigle", "devise", "slogan", "telephone", "email", "adresse", "annee", "version"].forEach(function (k) {
          if (rep && rep[k] !== undefined) SD.ecole[k] = rep[k];
        });
        el("aboutVersion").textContent = "Version " + (SD.ecole.version || "1.0.0");
        reussite(ecoleConfiguree ? "Établissement modifié avec succès ✅" : "Établissement configuré avec succès ✅");
        terminer();
      }, echec);
    });
  }

  /* ---------- Actions ---------- */
  el("aboutVersion").textContent = "Version " + (SD.ecole.version || "1.0.0");
  el("btnLogout").addEventListener("click", function () {
    if (window.API) window.API.deconnexion();
    sessionStorage.removeItem("sm_session");
    window.location.href = "../index.html";
  });
})();
