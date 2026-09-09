/* ============================================================
   SchoolManager — Annonces
   ============================================================ */

(function () {
  "use strict";

  var SM = window.SM;
  var SD = window.SD;

  function el(id) { return document.getElementById(id); }
  var deleteId = null;

  /* ---------- Rendu ---------- */
  function render() {
    var liste = SD.annonces.slice().sort(function (a, b) {
      return (a.date < b.date) ? 1 : (a.date > b.date ? -1 : 0);
    });
    if (!liste.length) {
      el("listAnnounces").innerHTML = '<div class="empty-state"><div class="e-ico">📢</div><h4>Aucune annonce publiée</h4>' +
        "<p>Cliquez sur « Publier une annonce » pour créer la première.</p></div>";
      return;
    }
    el("listAnnounces").innerHTML = liste.map(function (a) {
      var d = new Date(a.date + "T00:00:00");
      var dateTxt = d.toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
      return (
        '<div class="card announce-card' + (a.important ? " important" : "") + '">' +
        '  <div class="a-title">' +
        (a.important ? '<span class="badge badge-danger">🔥 Important</span>' : "") +
        '    <span>' + SM.escapeHtml(a.titre) + "</span>" +
        '    <button class="btn-icon danger" style="margin-left:auto" title="Supprimer" data-del="' + a.id + '">🗑️</button>' +
        "  </div>" +
        '  <div class="a-body">' + SM.escapeHtml(a.contenu) + "</div>" +
        '  <div class="a-meta">' +
        '    <span><span class="chip-plain">' + SM.escapeHtml(a.categorie) + "</span></span>" +
        "    <span>📅 " + dateTxt + "</span>" +
        "    <span>👤 " + SM.escapeHtml(a.auteur) + "</span>" +
        "  </div>" +
        "</div>"
      );
    }).join("");
  }
  render();

  /* ---------- Modale Publier ---------- */
  function resetForm() {
    el("fTitre").value = "";
    el("fCategorie").value = "Information";
    el("fContenu").value = "";
    el("fImportant").checked = false;
    el("wrapImportant").classList.remove("on");
    document.querySelectorAll(".field-error.show").forEach(function (x) { x.classList.remove("show"); });
    document.querySelectorAll(".input.invalid, .textarea.invalid").forEach(function (x) { x.classList.remove("invalid"); });
  }
  document.addEventListener("click", function (e) {
    if (e.target.closest('[data-open="modalAnnounce"]')) resetForm();
  });
  el("fImportant").addEventListener("change", function () {
    el("wrapImportant").classList.toggle("on", this.checked);
  });

  el("btnSaveAnnounce").addEventListener("click", function () {
    var titre = el("fTitre").value.trim();
    var contenu = el("fContenu").value.trim();
    var ok = true;
    if (!titre) { el("fTitre").classList.add("invalid"); el("errTitre").classList.add("show"); ok = false; }
    if (!contenu) { el("fContenu").classList.add("invalid"); el("errContenu").classList.add("show"); ok = false; }
    if (!ok) { SM.toast("Veuillez compléter les champs obligatoires.", "error"); return; }

    var sess = SM.getSession();
    var bouton = el("btnSaveAnnounce");
    bouton.disabled = true;
    bouton.textContent = "Publication…";
    API.creerAnnonce({
      titre: titre,
      contenu: contenu,
      categorie: el("fCategorie").value,
      date: new Date().toISOString().slice(0, 10),
      auteur: sess && sess.nom ? sess.nom : "Administration",
      important: el("fImportant").checked
    }).then(function (annonce) {
      SD.annonces.push(annonce);
      SM.closeModal("modalAnnounce");
      SM.toast("Annonce publiée avec succès ✅", "success");
      render();
    }).catch(function (err) {
      SM.toast("Publication impossible : " + (err && err.detail ? err.detail : "erreur réseau."), "error");
    }).then(function () {
      bouton.disabled = false;
      bouton.textContent = "🚀 Publier";
    });
  });

  /* ---------- Suppression ---------- */
  el("listAnnounces").addEventListener("click", function (e) {
    var btn = e.target.closest("[data-del]");
    if (!btn) return;
    deleteId = btn.getAttribute("data-del");
    var a = SD.annonces.find(function (x) { return x.id === deleteId; });
    el("delText").innerHTML = "L'annonce <b>" + SM.escapeHtml(a ? a.titre : "") + "</b> sera définitivement retirée.";
    SM.openModal("modalDel");
  });

  el("btnConfirmDel").addEventListener("click", function () {
    if (!deleteId) return;
    var bouton = el("btnConfirmDel");
    bouton.disabled = true;
    var id = deleteId;
    API.supprimerAnnonce(id).then(function () {
      var idx = SD.annonces.findIndex(function (x) { return x.id === id; });
      if (idx !== -1) SD.annonces.splice(idx, 1);
      SM.toast("Annonce supprimée.", "warning");
      SM.closeModal("modalDel");
      deleteId = null;
      render();
    }).catch(function (err) {
      SM.toast("Suppression impossible : " + (err && err.detail ? err.detail : "erreur réseau."), "error");
    }).then(function () {
      bouton.disabled = false;
    });
  });
})();
