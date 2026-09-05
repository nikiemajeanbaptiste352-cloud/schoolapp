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
  el("ecoleRows").innerHTML = lignes([
    ["Nom", SM.escapeHtml(SD.ecole.nom)],
    ["Sigle", SM.escapeHtml(SD.ecole.sigle)],
    ["Slogan", SM.escapeHtml(SD.ecole.slogan)],
    ["Adresse", SM.escapeHtml(SD.ecole.adresse)],
    ["Téléphone", SM.escapeHtml(SD.ecole.telephone)],
    ["Email", SM.escapeHtml(SD.ecole.email)],
    ["Devise", SM.escapeHtml(SD.ecole.devise)]
  ]);

  /* ---------- Année scolaire ---------- */
  el("anneeRows").innerHTML = lignes([
    ["Année scolaire", SM.escapeHtml(SD.ecole.annee)],
    ["Classes", SD.classes.length + " classes"],
    ["Élèves inscrits", SD.eleves.length + " élèves"],
    ["Enseignants", SD.enseignants.length + " professeurs"],
    ["Matières au programme", SD.matieres.length + " matières"],
    ["Évaluations", SD.EVALS.length + " par matière (" + SD.EVALS.join(", ") + ")"]
  ]);

  /* ---------- Session ---------- */
  var sess = SM.getSession() || {};
  var roleLabel = { Administrateur: "🛡️ Administrateur", Professeur: "👨‍🏫 Professeur", Élève: "👨‍🎓 Élève", Parent: "👨‍👩‍👧 Parent" };
  el("sessionRows").innerHTML = lignes([
    ["Connecté en tant que", SM.escapeHtml(sess.nom || "—")],
    ["Adresse email", SM.escapeHtml(sess.email || "—")],
    ["Rôle", roleLabel[sess.role] || SM.escapeHtml(sess.role || "—")]
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

  if (sess && sess.role === "Administrateur") {
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

  /* ---------- Actions ---------- */
  el("aboutVersion").textContent = "Version " + (SD.ecole.version || "1.0.0");
  el("btnLogout").addEventListener("click", function () {
    if (window.API) window.API.deconnexion();
    sessionStorage.removeItem("sm_session");
    window.location.href = "../index.html";
  });
})();
