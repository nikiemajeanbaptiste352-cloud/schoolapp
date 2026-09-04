/* ============================================================
   SchoolManager — Gestion des enseignants
   ============================================================ */

(function () {
  "use strict";

  var SM = window.SM;
  var SD = window.SD;
  var profs = SD.enseignants; // tableau vivant (démo)
  var editId = null;
  var deleteId = null;

  function el(id) { return document.getElementById(id); }

  /* ---------- Remplissage matière + classes ---------- */
  var selMatiere = el("fMatiere");
  SD.matieres.forEach(function (m) {
    var o = document.createElement("option");
    o.value = m.id;
    o.textContent = m.icone + " " + m.nom;
    selMatiere.appendChild(o);
  });

  var chipsWrap = el("chipsClasses");
  SD.classes.forEach(function (c) {
    var label = document.createElement("label");
    label.className = "chip-toggle";
    label.innerHTML = '<input type="checkbox" value="' + c.id + '"> ' + SM.escapeHtml(c.nom);
    label.addEventListener("change", function () {
      label.classList.toggle("on", label.querySelector("input").checked);
    });
    chipsWrap.appendChild(label);
  });

  function classesSelectionnees() {
    return Array.prototype.map.call(chipsWrap.querySelectorAll("input:checked"), function (i) { return i.value; });
  }
  function setClasses(liste) {
    chipsWrap.querySelectorAll("input").forEach(function (i) {
      i.checked = liste.indexOf(i.value) !== -1;
      i.closest(".chip-toggle").classList.toggle("on", i.checked);
    });
  }

  /* ---------- Compteurs ---------- */
  function compteurs() {
    var actifs = profs.filter(function (p) { return p.statut === "Actif"; }).length;
    var matieres = {};
    profs.forEach(function (p) { matieres[p.matiere] = true; });
    el("miniCounts").innerHTML =
      '<div class="mini-stat"><div class="v">' + profs.length + '</div><div class="l">Enseignants</div></div>' +
      '<div class="mini-stat"><div class="v">' + actifs + '</div><div class="l">Actifs</div></div>' +
      '<div class="mini-stat"><div class="v">' + (profs.length - actifs) + '</div><div class="l">Inactifs</div></div>' +
      '<div class="mini-stat"><div class="v">' + Object.keys(matieres).length + '</div><div class="l">Matières couvertes</div></div>';
  }

  /* ---------- Rendu ---------- */
  function render(liste) {
    var tbody = el("tableBody");
    if (!liste.length) {
      tbody.innerHTML =
        '<tr><td colspan="7"><div class="empty-state"><div class="e-ico">🔍</div><h4>Aucun enseignant trouvé</h4>' +
        "<p>Ajustez votre recherche ou ajoutez un nouvel enseignant.</p></div></td></tr>";
      el("countLabel").textContent = "0 enseignant";
      return;
    }
    tbody.innerHTML = liste.map(function (p) {
      var m = SD.getMatiere(p.matiere);
      var nomC = p.nom + " " + p.prenom;
      var chipsCls = p.classes.length
        ? p.classes.map(function (cid) {
            var c = SD.getClasse(cid);
            return '<span class="chip-plain">' + SM.escapeHtml(c ? c.nom : cid) + "</span>";
          }).join(" ")
        : '<span class="text-muted text-sm">—</span>';
      return (
        "<tr>" +
        '  <td class="fw-600">' + SM.escapeHtml(p.id) + "</td>" +
        "  <td><div class='cell-user'>" + SM.avatarHTML(nomC, "sm") +
        '    <div><div class="names">' + SM.escapeHtml(p.nom) + " " + SM.escapeHtml(p.prenom) +
        '      </div><div class="sub">' + SM.escapeHtml(p.email) + "</div></div></div></td>" +
        '  <td><div class="flex-center" style="justify-content:flex-start">' + (m ? m.icone + ' <span class="fw-600">' + SM.escapeHtml(m.nom) + "</span>" : "—") + "</div></td>" +
        '  <td><div class="c-counts" style="gap:4px">' + chipsCls + "</div></td>" +
        "  <td>" + SM.escapeHtml(p.tel) + "</td>" +
        "  <td>" + SM.badgeStatut(p.statut) + "</td>" +
        '  <td><div class="row-actions" style="justify-content:center">' +
        '    <button class="btn-icon primary-h" title="Modifier" data-edit="' + p.id + '">✏️</button>' +
        '    <button class="btn-icon danger" title="Supprimer" data-del="' + p.id + '">🗑️</button>' +
        "  </div></td>" +
        "</tr>"
      );
    }).join("");
    el("countLabel").textContent = liste.length + " enseignant" + (liste.length > 1 ? "s" : "") + " affiché" + (liste.length > 1 ? "s" : "");
  }

  function actualiser() {
    var q = el("searchInput").value.toLowerCase().trim();
    compteurs();
    if (!q) { render(profs); return; }
    var filtre = profs.filter(function (p) {
      var m = SD.getMatiere(p.matiere);
      var classesTxt = p.classes.map(function (cid) {
        var c = SD.getClasse(cid);
        return c ? c.nom : cid;
      }).join(" ");
      return (p.nom + " " + p.prenom + " " + p.id + " " + (m ? m.nom : "") + " " + classesTxt + " " + p.tel).toLowerCase().indexOf(q) !== -1;
    });
    render(filtre);
  }

  compteurs();
  render(profs);

  /* ---------- Recherche ---------- */
  el("searchInput").addEventListener("input", actualiser);

  /* ---------- Modale ---------- */
  function resetForm() {
    editId = null;
    el("modalTitle").textContent = "➕ Ajouter un enseignant";
    ["fId", "fNom", "fPrenom", "fTel", "fEmail"].forEach(function (id) { el(id).value = ""; });
    el("fSexe").value = "M";
    el("fStatut").value = "Actif";
    el("fMatiere").value = "S1";
    setClasses([]);
    clearErreurs();
  }
  function clearErreurs() {
    document.querySelectorAll(".field-error.show").forEach(function (x) { x.classList.remove("show"); });
    document.querySelectorAll(".input.invalid").forEach(function (x) { x.classList.remove("invalid"); });
  }
  function ouvrirProf(id) {
    resetForm();
    var p = SD.getEnseignant(id);
    if (!p) return;
    editId = id;
    el("modalTitle").textContent = "✏️ Modifier l'enseignant " + p.id;
    el("fId").value = p.id;
    el("fNom").value = p.nom;
    el("fPrenom").value = p.prenom;
    el("fSexe").value = p.sexe;
    el("fTel").value = p.tel;
    el("fEmail").value = p.email;
    el("fStatut").value = p.statut;
    el("fMatiere").value = p.matiere;
    setClasses(p.classes);
    SM.openModal("modalProf");
  }

  // Reset du formulaire à l'ouverture via le bouton « Ajouter »
  document.addEventListener("click", function (e) {
    if (e.target.closest('[data-open="modalProf"]')) resetForm();
  });

  /* ---------- Actions tableau ---------- */
  el("tableBody").addEventListener("click", function (ev) {
    var btn = ev.target.closest("button[data-edit], button[data-del]");
    if (!btn) return;
    var id = btn.getAttribute("data-edit") || btn.getAttribute("data-del");
    if (btn.hasAttribute("data-edit")) {
      ouvrirProf(id);
    } else {
      deleteId = id;
      var p = SD.getEnseignant(id);
      el("delText").innerHTML = "L'enseignant <b>" + SM.escapeHtml(p.nom + " " + p.prenom) + "</b> (" + p.id + ") sera définitivement retiré de la liste.";
      SM.openModal("modalDel");
    }
  });

  /* ---------- Validation ---------- */
  function valider() {
    var ok = true;
    [["fNom", "errNom"], ["fPrenom", "errPrenom"]].forEach(function (c) {
      if (!el(c[0]).value.trim()) {
        el(c[0]).classList.add("invalid");
        el(c[1]).classList.add("show");
        ok = false;
      }
    });
    if (!el("fMatiere").value) {
      el("fMatiere").classList.add("invalid");
      el("errMatiere").classList.add("show");
      ok = false;
    }
    return ok;
  }

  /* ---------- Enregistrement ---------- */
  el("btnSaveProf").addEventListener("click", function () {
    if (!valider()) { SM.toast("Veuillez compléter les champs obligatoires.", "error"); return; }
    var d = {
      nom: el("fNom").value.trim(),
      prenom: el("fPrenom").value.trim(),
      sexe: el("fSexe").value,
      tel: el("fTel").value.trim() || "—",
      email: el("fEmail").value.trim() || "—",
      matiere: el("fMatiere").value,
      classes: classesSelectionnees(),
      statut: el("fStatut").value
    };
    if (editId) {
      var p = SD.getEnseignant(editId);
      Object.assign(p, d);
      SM.toast("Enseignant " + editId + " modifié avec succès ✅", "success");
    } else {
      var max = 0;
      profs.forEach(function (x) {
        var n = parseInt(x.id.replace("T", ""), 10);
        if (n > max) max = n;
      });
      d.id = "T" + String(max + 1).padStart(3, "0");
      profs.push(d);
      SM.toast("Enseignant " + d.id + " ajouté avec succès ✅", "success");
    }
    SM.closeModal("modalProf");
    actualiser();
  });

  /* ---------- Suppression ---------- */
  el("btnConfirmDel").addEventListener("click", function () {
    if (!deleteId) return;
    var idx = profs.findIndex(function (x) { return x.id === deleteId; });
    if (idx !== -1) profs.splice(idx, 1);
    SM.toast("Enseignant " + deleteId + " supprimé.", "warning");
    SM.closeModal("modalDel");
    deleteId = null;
    actualiser();
  });
})();
