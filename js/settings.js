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

  /* ---------- Actions ---------- */
  el("aboutVersion").textContent = "Version " + (SD.ecole.version || "1.0.0");
  el("btnLogout").addEventListener("click", function () {
    if (window.API) window.API.deconnexion();
    sessionStorage.removeItem("sm_session");
    window.location.href = "../index.html";
  });
})();
