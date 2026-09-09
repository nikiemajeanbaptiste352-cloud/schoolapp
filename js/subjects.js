/* ============================================================
   SchoolManager — Matières (tableau + gestion admin)
   ============================================================ */

(function () {
  "use strict";

  var SM = window.SM;
  var SD = window.SD;

  function el(id) { return document.getElementById(id); }

  var sess = SM.getSession() || {};
  var estAdmin = sess.role === "Administrateur";
  var editId = null;
  var deleteId = null;

  /* Classes qui suivent une matière donnée */
  function classesDeMatiere(matId) {
    return SD.classes.filter(function (c) {
      return SD.matieresDeClasse(c.id).some(function (m) { return m.id === matId; });
    });
  }

  /* ---------- Compteurs ---------- */
  function compteurs() {
    var coefTotal = SD.matieres.reduce(function (s, m) { return s + m.coef; }, 0);
    if (el("coefTotal")) el("coefTotal").textContent = coefTotal;
    el("miniCounts").innerHTML =
      '<div class="mini-stat"><div class="v">' + SD.matieres.length + '</div><div class="l">Matières</div></div>' +
      '<div class="mini-stat"><div class="v">' + coefTotal + '</div><div class="l">Coef. total</div></div>' +
      '<div class="mini-stat"><div class="v">' + SD.classes.length + '</div><div class="l">Classes</div></div>' +
      '<div class="mini-stat"><div class="v">' + SD.enseignants.length + '</div><div class="l">Enseignants</div></div>';
  }
  compteurs();

  /* ---------- Rendu ---------- */
  function render() {
    el("tableBody").innerHTML = SD.matieres.map(function (m) {
      var profs = SD.enseignants.filter(function (e) { return e.matiere === m.id; });
      var classes = classesDeMatiere(m.id);
      var btnAdmin = estAdmin
        ? '<td><div class="row-actions" style="justify-content:center">' +
          '  <button class="btn-icon primary-h" title="Modifier" data-edit="' + m.id + '">✏️</button>' +
          '  <button class="btn-icon danger" title="Supprimer" data-del="' + m.id + '">🗑️</button>' +
          "</div></td>"
        : "";
      return (
        "<tr>" +
        '  <td><div class="flex-center" style="justify-content:flex-start;gap:10px"><span style="font-size:22px">' + m.icone + '</span>' +
        '    <div><div class="fw-600">' + SM.escapeHtml(m.nom) + '</div><div class="sub text-muted" style="font-size:12px">' + SM.escapeHtml(m.id) + "</div></div></div></td>" +
        '  <td class="text-center"><span class="chip">' + m.coef + "</span></td>" +
        "  <td>" +
        (profs.length
          ? profs.map(function (p) {
              return '<div class="cell-user">' + SM.avatarHTML(p.nom + " " + p.prenom, "sm") +
                '<div><div class="names">' + SM.escapeHtml(p.prenom + " " + p.nom) + '</div><div class="sub">' + SM.escapeHtml(p.id) + "</div></div></div>";
            }).join("")
          : '<span class="text-muted text-sm">Aucun enseignant attitré</span>') +
        "</td>" +
        "  <td><div class='c-counts' style='gap:4px'>" +
        (classes.length
          ? classes.map(function (c) { return '<span class="chip-plain">' + SM.escapeHtml(c.nom) + "</span>"; }).join(" ")
          : '<span class="text-muted text-sm">—</span>') +
        "</div></td>" +
        btnAdmin +
        "</tr>"
      );
    }).join("");
  }
  render();

  // Bouton « Ajouter » et colonne Actions : visibles pour l'administrateur
  if (estAdmin) {
    if (el("btnAddMatiere")) el("btnAddMatiere").style.display = "";
    var th = el("thActions");
    if (th) th.style.display = "";
  }

  /* ---------- Formulaire ajout / modification ---------- */
  function clearErreurs() {
    document.querySelectorAll(".field-error.show").forEach(function (x) { x.classList.remove("show"); });
    document.querySelectorAll(".input.invalid").forEach(function (x) { x.classList.remove("invalid"); });
  }
  function resetForm() {
    editId = null;
    el("matiereModalTitle").textContent = "➕ Ajouter une matière";
    el("matiereId").value = "";
    el("matiereNom").value = "";
    el("matiereCoef").value = "1";
    el("matiereIcone").value = "📘";
    el("matiereCouleur").value = "blue";
    el("matiereCode").value = "(auto)";
    clearErreurs();
    SM.openModal("modalMatiereEdit");
  }
  function ouvrirEdition(id) {
    var m = SD.getMatiere(id);
    if (!m) return;
    editId = id;
    el("matiereModalTitle").textContent = "✏️ Modifier la matière " + m.id;
    el("matiereId").value = m.id;
    el("matiereNom").value = m.nom;
    el("matiereCoef").value = m.coef;
    el("matiereIcone").value = m.icone || "📘";
    el("matiereCouleur").value = m.couleur || "blue";
    el("matiereCode").value = m.id;
    clearErreurs();
    SM.openModal("modalMatiereEdit");
  }

  if (estAdmin && el("btnAddMatiere")) {
    el("btnAddMatiere").addEventListener("click", resetForm);
  }

  /* ---------- Actions du tableau ---------- */
  el("tableBody").addEventListener("click", function (ev) {
    if (!estAdmin) return;
    var btn = ev.target.closest("button[data-edit], button[data-del]");
    if (!btn) return;
    var id = btn.getAttribute("data-edit") || btn.getAttribute("data-del");
    if (btn.hasAttribute("data-edit")) {
      ouvrirEdition(id);
    } else {
      deleteId = id;
      var m = SD.getMatiere(id);
      var profs = SD.enseignants.filter(function (e) { return e.matiere === id; });
      el("delMatiereText").innerHTML =
        "La matière <b>" + SM.escapeHtml(m ? m.nom : id) + "</b> (" + id + ") sera retirée des programmes." +
        (profs.length
          ? ' <div class="mt-8 text-sm">Les ' + profs.length + " enseignant(s) rattaché(s) seront détachés (matière : —).</div>"
          : "");
      SM.openModal("modalDelMatiere");
    }
  });

  /* ---------- Enregistrement ---------- */
  el("btnSaveMatiere").addEventListener("click", function () {
    clearErreurs();
    var nom = el("matiereNom").value.trim();
    var ok = true;
    if (!nom) {
      el("matiereNom").classList.add("invalid");
      el("errMatiereNom").classList.add("show");
      ok = false;
    }
    var coef = parseInt(el("matiereCoef").value, 10);
    if (!coef || coef < 1 || coef > 20) {
      el("matiereCoef").classList.add("invalid");
      el("errMatiereCoef").classList.add("show");
      ok = false;
    }
    if (!ok) { SM.toast("Veuillez corriger le formulaire.", "error"); return; }

    var d = {
      nom: nom,
      coef: coef,
      icone: el("matiereIcone").value.trim() || "📘",
      couleur: el("matiereCouleur").value
    };
    var bouton = el("btnSaveMatiere");
    bouton.disabled = true;
    bouton.textContent = "Enregistrement…";

    function terminer() { bouton.disabled = false; bouton.textContent = "💾 Enregistrer"; }
    function reussite(message) {
      SM.closeModal("modalMatiereEdit");
      SM.toast(message, "success");
      compteurs();
      render();
    }
    function echec(err) {
      SM.toast("Enregistrement impossible : " + (err && err.detail ? err.detail : "erreur réseau."), "error");
      terminer();
    }

    if (editId) {
      API.majMatiere(editId, d).then(function (rep) {
        var idx = SD.matieres.findIndex(function (x) { return x.id === editId; });
        if (idx !== -1) SD.matieres[idx] = rep; else SD.matieres.push(rep);
        reussite("Matière " + editId + " modifiée ✅");
        terminer();
      }, echec);
    } else {
      API.creerMatiere(d).then(function (rep) {
        SD.matieres.push(rep);
        reussite("Matière " + rep.id + " ajoutée ✅");
        terminer();
      }, echec);
    }
  });

  /* ---------- Suppression ---------- */
  el("btnConfirmDelMatiere").addEventListener("click", function () {
    if (!deleteId) return;
    var bouton = el("btnConfirmDelMatiere");
    bouton.disabled = true;
    var id = deleteId;
    API.supprimerMatiere(id).then(function () {
      var idx = SD.matieres.findIndex(function (x) { return x.id === id; });
      if (idx !== -1) SD.matieres.splice(idx, 1);
      // Détache localement les enseignants de cette matière (le serveur l'a fait)
      SD.enseignants.forEach(function (e) { if (e.matiere === id) e.matiere = null; });
      SM.toast("Matière " + id + " supprimée.", "warning");
      SM.closeModal("modalDelMatiere");
      deleteId = null;
      compteurs();
      render();
    }).catch(function (err) {
      SM.toast("Suppression impossible : " + (err && err.detail ? err.detail : "erreur réseau."), "error");
    }).then(function () {
      bouton.disabled = false;
    });
  });
})();
