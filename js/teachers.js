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

  // Droit d'écriture décidé par le serveur (capacités de GET /api/v1/etat).
  var peutEcrire = SM.peut("enseignants.ecrire");

  // Un professeur retrouve sa propre fiche dans l'annuaire : on la signale au
  // lieu de la lui laisser chercher. La liste complète est conservée (le
  // serveur accorde l'annuaire au personnel encadrant).
  var role = SM.roleCourant();
  var estProf = role === "Professeur";
  var maFiche = estProf ? SM.monEnseignant(SD) : null;
  var monId = maFiche ? maFiche.id : null;

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
    // Un professeur suit ses propres classes : les compteurs parlent de lui,
    // pas de la gestion administrative de l'établissement.
    if (estProf && maFiche) {
      var mesEleves = maFiche.classes.reduce(function (n, cid) {
        return n + SD.elevesDeClasse(cid).length;
      }, 0);
      el("miniCounts").innerHTML =
        '<div class="mini-stat"><div class="v">' + profs.length + '</div><div class="l">Enseignants</div></div>' +
        '<div class="mini-stat"><div class="v">' + maFiche.classes.length + '</div><div class="l">Mes classes</div></div>' +
        '<div class="mini-stat"><div class="v">' + mesEleves + '</div><div class="l">Mes élèves</div></div>' +
        '<div class="mini-stat"><div class="v">' + Object.keys(matieres).length + '</div><div class="l">Matières couvertes</div></div>';
      return;
    }
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
        '<tr><td colspan="' + (peutEcrire ? 7 : 6) + '"><div class="empty-state"><div class="e-ico">🔍</div><h4>Aucun enseignant trouvé</h4>' +
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
      // Actions d'écriture : uniquement si le serveur les accorde.
      var actions = peutEcrire
        ? '    <button class="btn-icon primary-h" title="Modifier" data-edit="' + p.id + '">✏️</button>' +
          '    <button class="btn-icon danger" title="Supprimer" data-del="' + p.id + '">🗑️</button>'
        : '<span class="text-muted text-sm">—</span>';
      var badgeMoi = p.id === monId ? ' <span class="badge badge-success">Vous</span>' : "";
      return (
        "<tr>" +
        '  <td class="fw-600">' + SM.escapeHtml(p.id) + "</td>" +
        "  <td><div class='cell-user'>" + SM.avatarHTML(nomC, "sm") +
        '    <div><div class="names">' + SM.escapeHtml(p.nom) + " " + SM.escapeHtml(p.prenom) + badgeMoi +
        '      </div><div class="sub">' + SM.escapeHtml(p.email) + "</div></div></div></td>" +
        '  <td><div class="flex-center" style="justify-content:flex-start">' + (m ? m.icone + ' <span class="fw-600">' + SM.escapeHtml(m.nom) + "</span>" : "—") + "</div></td>" +
        '  <td><div class="c-counts" style="gap:4px">' + chipsCls + "</div></td>" +
        "  <td>" + SM.escapeHtml(p.tel) + "</td>" +
        "  <td>" + SM.badgeStatut(p.statut) + "</td>" +
        '  <td><div class="row-actions" style="justify-content:center">' +
        actions +
        "  </div></td>" +
        "</tr>"
      );
    }).join("");
    el("countLabel").textContent = liste.length + " enseignant" + (liste.length > 1 ? "s" : "") + " affiché" + (liste.length > 1 ? "s" : "");
    // Sans droit d'écriture, la colonne « Actions » n'afficherait qu'un
    // tiret : on la masque avec ses cellules pour ne pas décaler le tableau.
    var tdsActions = tbody.querySelectorAll("tr > td:nth-child(7)");
    for (var j = 0; j < tdsActions.length; j++) tdsActions[j].style.display = peutEcrire ? "" : "none";
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

  // En-tête « Actions » : la page le masque par défaut, on ne le montre que
  // si le serveur accorde l'écriture (l'annuaire peut être servi en lecture).
  if (el("thActions")) el("thActions").style.display = peutEcrire ? "" : "none";

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
    var bouton = el("btnSaveProf");
    bouton.disabled = true;
    bouton.textContent = "Enregistrement…";

    function terminer() {
      bouton.disabled = false;
      bouton.textContent = "💾 Enregistrer";
    }
    function reussite(message) {
      SM.closeModal("modalProf");
      SM.toast(message, "success");
      actualiser();
    }
    function echec(err) {
      SM.toast("Enregistrement impossible : " + (err && err.detail ? err.detail : "erreur réseau."), "error");
      terminer();
    }

    if (editId) {
      API.majEnseignant(editId, d).then(function (rep) {
        var idx = profs.findIndex(function (x) { return x.id === editId; });
        if (idx !== -1) profs[idx] = rep; else profs.push(rep);
        reussite("Enseignant " + editId + " modifié avec succès ✅");
        terminer();
      }, echec);
    } else {
      API.creerEnseignant(d).then(function (rep) {
        profs.push(rep);
        reussite("Enseignant " + rep.id + " ajouté avec succès ✅");
        terminer();
      }, echec);
    }
  });

  /* ---------- Suppression ---------- */
  el("btnConfirmDel").addEventListener("click", function () {
    if (!deleteId) return;
    var bouton = el("btnConfirmDel");
    bouton.disabled = true;
    var id = deleteId;
    API.supprimerEnseignant(id).then(function () {
      var idx = profs.findIndex(function (x) { return x.id === id; });
      if (idx !== -1) profs.splice(idx, 1);
      SM.toast("Enseignant " + id + " supprimé.", "warning");
      SM.closeModal("modalDel");
      deleteId = null;
      actualiser();
    }).catch(function (err) {
      SM.toast("Suppression impossible : " + (err && err.detail ? err.detail : "erreur réseau."), "error");
    }).then(function () {
      bouton.disabled = false;
    });
  });
})();
