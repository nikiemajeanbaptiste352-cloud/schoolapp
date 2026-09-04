/* ============================================================
   SchoolManager — Gestion des élèves
   ============================================================ */

(function () {
  "use strict";

  var SM = window.SM;
  var SD = window.SD;
  var eleves = SD.eleves; // tableau vivant (démo)

  /* ---------- Remplissage du sélecteur de classe ---------- */
  var selClasse = document.getElementById("fClasse");
  SD.classes.forEach(function (c) {
    var o = document.createElement("option");
    o.value = c.id;
    o.textContent = c.nom;
    selClasse.appendChild(o);
  });

  /* ---------- Compteurs ---------- */
  var actifs = eleves.filter(function (e) { return e.statut === "Actif"; }).length;
  document.getElementById("miniCounts").innerHTML =
    '<div class="mini-stat"><div class="v">' + eleves.length + '</div><div class="l">Total élèves</div></div>' +
    '<div class="mini-stat"><div class="v">' + actifs + '</div><div class="l">Actifs</div></div>' +
    '<div class="mini-stat"><div class="v">' + (eleves.length - actifs) + '</div><div class="l">Inactifs</div></div>' +
    '<div class="mini-stat"><div class="v">' + SD.classes.length + '</div><div class="l">Classes</div></div>';

  /* ---------- Rendu ---------- */
  function render(liste) {
    var tbody = document.getElementById("tableBody");
    if (!liste.length) {
      tbody.innerHTML =
        '<tr><td colspan="8"><div class="empty-state"><div class="e-ico">🔍</div><h4>Aucun élève trouvé</h4>' +
        "<p>Ajustez votre recherche ou ajoutez un nouvel élève.</p></div></td></tr>";
      document.getElementById("countLabel").textContent = "0 élève";
      return;
    }
    tbody.innerHTML = liste.map(function (e) {
      var cls = SD.getClasse(e.classe);
      var nomC = e.nom + " " + e.prenom;
      return (
        "<tr>" +
        '  <td class="fw-600">' + SM.escapeHtml(e.id) + "</td>" +
        "  <td><div class='cell-user'>" + SM.avatarHTML(nomC, "sm") +
        '    <div><div class="names">' + SM.escapeHtml(e.nom) + " " + SM.escapeHtml(e.prenom) +
        '      </div><div class="sub">Responsable : ' + SM.escapeHtml(e.parent.nom) + "</div></div></div></td>" +
        '  <td>' + (e.sexe === "M" ? '<span class="badge badge-info">♂</span>' : '<span class="badge badge-warning">♀</span>') + "</td>" +
        '  <td>' + SM.fmtDate(e.naissance) + "</td>" +
        '  <td><span class="chip">' + SM.escapeHtml(cls ? cls.nom : e.classe) + "</span></td>" +
        "  <td>" + SM.escapeHtml(e.parent.tel) + "</td>" +
        "  <td>" + SM.badgeStatut(e.statut) + "</td>" +
        '  <td><div class="row-actions" style="justify-content:center">' +
        '    <button class="btn-icon primary-h" title="Voir la fiche" data-view="' + e.id + '">👁️</button>' +
        '    <button class="btn-icon primary-h" title="Modifier" data-edit="' + e.id + '">✏️</button>' +
        '    <button class="btn-icon danger" title="Supprimer" data-del="' + e.id + '">🗑️</button>' +
        "  </div></td>" +
        "</tr>"
      );
    }).join("");
    document.getElementById("countLabel").textContent = liste.length + " élève" + (liste.length > 1 ? "s" : "") + " affiché" + (liste.length > 1 ? "s" : "");
  }

  render(eleves);

  /* ---------- Recherche ---------- */
  document.getElementById("searchInput").addEventListener("input", function () {
    var q = this.value.toLowerCase().trim();
    if (!q) { render(eleves); return; }
    var filtre = eleves.filter(function (e) {
      var cls = SD.getClasse(e.classe);
      return (e.nom + " " + e.prenom + " " + e.id + " " + (cls ? cls.nom : "") + " " + e.parent.tel).toLowerCase().indexOf(q) !== -1;
    });
    render(filtre);
  });

  /* ---------- Modale : état édition ---------- */
  var editId = null;
  var deleteId = null;

  function resetForm() {
    editId = null;
    document.getElementById("modalTitle").textContent = "➕ Ajouter un élève";
    ["fId", "fNom", "fPrenom", "fNaissance", "fParent", "fTel", "fEmail"].forEach(function (id) {
      var el = document.getElementById(id);
      if (el.tagName === "SELECT") el.value = "";
      else el.value = "";
    });
    el("fClasse").value = "3A";
    el("fStatut").value = "Actif";
    el("fSexe").value = "M";
    clearErreurs();
  }
  function el(id) { return document.getElementById(id); }
  function clearErreurs() {
    document.querySelectorAll(".field-error.show").forEach(function (x) { x.classList.remove("show"); });
    document.querySelectorAll(".input.invalid").forEach(function (x) { x.classList.remove("invalid"); });
  }

  // Ouverture modale : bouton « Ajouter » (délégué global data-open) → reset avant
  document.addEventListener("click", function (e) {
    if (e.target.closest('[data-open="modalEleve"]')) resetForm();
  });

  function openEleve(id) {
    resetForm();
    var e = SD.getEleve(id);
    if (!e) return;
    editId = id;
    el("modalTitle").textContent = "✏️ Modifier l'élève " + e.id;
    el("fId").value = e.id;
    el("fNom").value = e.nom;
    el("fPrenom").value = e.prenom;
    el("fSexe").value = e.sexe;
    el("fNaissance").value = e.naissance;
    el("fClasse").value = e.classe;
    el("fStatut").value = e.statut;
    el("fParent").value = e.parent.nom;
    el("fTel").value = e.parent.tel;
    el("fEmail").value = e.parent.email;
    SM.openModal("modalEleve");
  }

  /* ---------- Délégation actions du tableau ---------- */
  document.getElementById("tableBody").addEventListener("click", function (ev) {
    var btn = ev.target.closest("button[data-view], button[data-edit], button[data-del]");
    if (!btn) return;
    var id = btn.getAttribute("data-view") || btn.getAttribute("data-edit") || btn.getAttribute("data-del");
    if (btn.hasAttribute("data-view")) {
      window.location.href = "student-profile.html?id=" + id;
    } else if (btn.hasAttribute("data-edit")) {
      openEleve(id);
    } else {
      deleteId = id;
      var e = SD.getEleve(id);
      document.getElementById("delText").innerHTML = "L'élève <b>" + SM.escapeHtml(e.nom + " " + e.prenom) + "</b> (" + e.id + ") sera définitivement retiré de la liste.";
      SM.openModal("modalDel");
    }
  });

  /* ---------- Validation ---------- */
  function valider() {
    var ok = true;
    var champs = [
      ["fNom", "errNom"],
      ["fPrenom", "errPrenom"],
      ["fNaissance", "errNaissance"]
    ];
    champs.forEach(function (c) {
      var v = el(c[0]).value.trim();
      if (!v) {
        el(c[0]).classList.add("invalid");
        el(c[1]).classList.add("show");
        ok = false;
      }
    });
    return ok;
  }

  /* ---------- Enregistrement ---------- */
  document.getElementById("btnSaveEleve").addEventListener("click", function () {
    if (!valider()) { SM.toast("Veuillez compléter les champs obligatoires.", "error"); return; }
    var d = {
      nom: el("fNom").value.trim(),
      prenom: el("fPrenom").value.trim(),
      sexe: el("fSexe").value,
      naissance: el("fNaissance").value,
      classe: el("fClasse").value,
      statut: el("fStatut").value
    };
    if (editId) {
      var e = SD.getEleve(editId);
      Object.assign(e, d);
      e.parent.nom = el("fParent").value.trim() || e.parent.nom;
      e.parent.tel = el("fTel").value.trim() || e.parent.tel;
      e.parent.email = el("fEmail").value.trim() || e.parent.email;
      SM.toast("Élève " + editId + " modifié avec succès ✅", "success");
    } else {
      var max = 0;
      SD.eleves.forEach(function (x) {
        var n = parseInt(x.id.replace("EL", ""), 10);
        if (n > max) max = n;
      });
      var nouvelId = "EL" + String(max + 1).padStart(3, "0");
      SD.eleves.push({
        id: nouvelId,
        nom: d.nom,
        prenom: d.prenom,
        sexe: d.sexe,
        naissance: d.naissance,
        classe: d.classe,
        statut: d.statut,
        inscription: new Date().toISOString().slice(0, 10),
        parent: {
          nom: el("fParent").value.trim() || "—",
          lien: "Tuteur",
          tel: el("fTel").value.trim() || "—",
          email: el("fEmail").value.trim() || "—",
          profession: "—",
          adresse: "—"
        }
      });
      SM.toast("Élève " + nouvelId + " ajouté avec succès ✅", "success");
    }
    SM.closeAllModals();
    actualiser();
  });

  /* ---------- Suppression ---------- */
  document.getElementById("btnConfirmDel").addEventListener("click", function () {
    if (!deleteId) return;
    var pos = SD.eleves.findIndex(function (x) { return x.id === deleteId; });
    if (pos !== -1) {
      SD.eleves.splice(pos, 1);
      SM.toast("Élève " + deleteId + " supprimé.", "success");
    }
    deleteId = null;
    SM.closeAllModals();
    actualiser();
  });

  function actualiser() {
    // Met à jour les compteurs
    var nbActifs = eleves.filter(function (e) { return e.statut === "Actif"; }).length;
    document.getElementById("miniCounts").innerHTML =
      '<div class="mini-stat"><div class="v">' + eleves.length + '</div><div class="l">Total élèves</div></div>' +
      '<div class="mini-stat"><div class="v">' + nbActifs + '</div><div class="l">Actifs</div></div>' +
      '<div class="mini-stat"><div class="v">' + (eleves.length - nbActifs) + '</div><div class="l">Inactifs</div></div>' +
      '<div class="mini-stat"><div class="v">' + SD.classes.length + '</div><div class="l">Classes</div></div>';
    var q = document.getElementById("searchInput").value.trim().toLowerCase();
    render(q ? eleves.filter(function (e) { return (e.nom + " " + e.prenom + " " + e.id).toLowerCase().indexOf(q) !== -1; }) : eleves);
  }

  // Champ erreur : revalidation en direct
  ["fNom", "fPrenom", "fNaissance"].forEach(function (id) {
    document.getElementById(id).addEventListener("input", function () {
      this.classList.remove("invalid");
      this.parentElement.querySelector(".field-error").classList.remove("show");
    });
  });
})();
