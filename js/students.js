/* ============================================================
   SchoolManager — Gestion des élèves
   ============================================================ */

(function () {
  "use strict";

  var SM = window.SM;
  var SD = window.SD;
  var eleves = SD.eleves; // tableau vivant (démo)

  // Droit d'écriture décidé par le serveur (capacités de GET /api/v1/etat) :
  // un élève ou un parent consulte sa fiche mais ne la modifie pas.
  var peutEcrire = SM.peut("eleves.ecrire");
  // Périmètre réduit (élève, parent) : la page parle d'un dossier, pas d'un
  // annuaire. Le téléphone du responsable relève de la gestion administrative.
  var estFamille = SM.porteeEleves() !== "tous";

  /* ---------- Remplissage du sélecteur de classe ---------- */
  var selClasse = document.getElementById("fClasse");
  SD.classes.forEach(function (c) {
    var o = document.createElement("option");
    o.value = c.id;
    o.textContent = c.nom;
    selClasse.appendChild(o);
  });

  /* ---------- Compteurs ----------
     Une direction compte ses effectifs ; un élève ou un parent suit les
     résultats de sa scolarité. Les mêmes quatre cases ne peuvent pas servir
     aux deux. */
  if (estFamille && eleves.length) {
    var premier = eleves[0];
    var moyF = SD.moyennesEleve(premier.id);
    var classeF = SD.getClasse(premier.classe);
    document.getElementById("miniCounts").innerHTML =
      '<div class="mini-stat"><div class="v">' + SM.escapeHtml(classeF ? classeF.nom : premier.classe) + '</div><div class="l">Classe</div></div>' +
      '<div class="mini-stat"><div class="v">' + moyF.generale.toFixed(2) + '</div><div class="l">Moyenne /20</div></div>' +
      '<div class="mini-stat"><div class="v">' + SD.tauxPresence(premier.id) + '%</div><div class="l">Présence</div></div>' +
      '<div class="mini-stat"><div class="v">' + (premier.statut === "Actif" ? "✅" : "⏸️") + '</div><div class="l">' + SM.escapeHtml(premier.statut || "—") + "</div></div>";
  } else {
    var actifs = eleves.filter(function (e) { return e.statut === "Actif"; }).length;
    document.getElementById("miniCounts").innerHTML =
      '<div class="mini-stat"><div class="v">' + eleves.length + '</div><div class="l">Total élèves</div></div>' +
      '<div class="mini-stat"><div class="v">' + actifs + '</div><div class="l">Actifs</div></div>' +
      '<div class="mini-stat"><div class="v">' + (eleves.length - actifs) + '</div><div class="l">Inactifs</div></div>' +
      '<div class="mini-stat"><div class="v">' + SD.classes.length + '</div><div class="l">Classes</div></div>';
  }

  /* ---------- Rendu ---------- */
  function render(liste) {
    var tbody = document.getElementById("tableBody");
    if (!liste.length) {
      tbody.innerHTML =
        '<tr><td colspan="' + (estFamille ? 7 : 8) + '"><div class="empty-state"><div class="e-ico">🔍</div><h4>Aucun élève trouvé</h4>' +
        "<p>" + (estFamille
          ? "Aucun dossier d'élève n'est rattaché à votre compte."
          : "Ajustez votre recherche ou ajoutez un nouvel élève.") + "</p></div></td></tr>";
      document.getElementById("countLabel").textContent = "0 élève";
      return;
    }
    tbody.innerHTML = liste.map(function (e) {
      var cls = SD.getClasse(e.classe);
      var nomC = e.nom + " " + e.prenom;
      // Actions d'écriture : proposées uniquement si le serveur les accorde
      // (un élève ou un parent consulte sa fiche, il ne la modifie pas).
      var actions = peutEcrire
        ? '    <button class="btn-icon primary-h" title="Modifier" data-edit="' + e.id + '">✏️</button>' +
          '    <button class="btn-icon danger" title="Supprimer" data-del="' + e.id + '">🗑️</button>'
        : "";
      return (
        "<tr>" +
        '  <td class="fw-600">' + SM.escapeHtml(e.id) + "</td>" +
        "  <td><div class='cell-user'>" + SM.avatarHTML(nomC, "sm") +
        '    <div><div class="names">' + SM.escapeHtml(e.nom) + " " + SM.escapeHtml(e.prenom) +
        '      </div><div class="sub">Responsable : ' + SM.escapeHtml(e.parent.nom) + "</div></div></div></td>" +
        '  <td>' + (e.sexe === "M" ? '<span class="badge badge-info">♂</span>' : '<span class="badge badge-warning">♀</span>') + "</td>" +
        '  <td>' + SM.fmtDate(e.naissance) + "</td>" +
        '  <td><span class="chip">' + SM.escapeHtml(cls ? cls.nom : e.classe) + "</span></td>" +
        (estFamille ? "<td></td>" : "  <td>" + SM.escapeHtml(e.parent.tel) + "</td>") +
        "  <td>" + SM.badgeStatut(e.statut) + "</td>" +
        '  <td><div class="row-actions" style="justify-content:center">' +
        '    <button class="btn-icon primary-h" title="Voir la fiche" data-view="' + e.id + '">👁️</button>' +
        actions +
        "  </div></td>" +
        "</tr>"
      );
    }).join("");
    // Le téléphone du responsable (6e colonne) n'est pas montré hors
    // périmètre : on masque l'en-tête et la cellule ensemble, sinon les
    // colonnes se décalent.
    var ths = document.querySelectorAll("table.data thead th");
    if (ths.length > 5) ths[5].style.display = estFamille ? "none" : "";
    var tds = tbody.querySelectorAll("tr > td:nth-child(6)");
    for (var i = 0; i < tds.length; i++) tds[i].style.display = estFamille ? "none" : "";
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
    el("fClasse").value = selClasse.options.length ? selClasse.options[0].value : "";
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
  // Reconstitue la forme canonique locale attendue par le rendu (le serveur
  // renvoie la fiche enrichie : classeNom, tauxPresence, parent.id…).
  function normaliserEleve(e) {
    var p = e.parent || {};
    return {
      id: e.id,
      nom: e.nom,
      prenom: e.prenom,
      sexe: e.sexe,
      naissance: e.naissance,
      classe: e.classe,
      statut: e.statut,
      inscription: e.inscription || new Date().toISOString().slice(0, 10),
      parent: {
        nom: p.nom || "—",
        lien: p.lien || "Tuteur",
        tel: p.tel || "—",
        email: p.email || "—",
        profession: p.profession || "—",
        adresse: p.adresse || "—"
      }
    };
  }
  document.getElementById("btnSaveEleve").addEventListener("click", function () {
    if (!valider()) { SM.toast("Veuillez compléter les champs obligatoires.", "error"); return; }
    if (!el("fClasse").value) {
      SM.toast("Aucune classe disponible : créez d'abord le référentiel (classes).", "error");
      return;
    }
    var edite = editId ? SD.getEleve(editId) : null;
    var parentActuel = (edite && edite.parent) || {};
    var d = {
      nom: el("fNom").value.trim(),
      prenom: el("fPrenom").value.trim(),
      sexe: el("fSexe").value,
      naissance: el("fNaissance").value,
      classe: el("fClasse").value,
      statut: el("fStatut").value,
      parent: {
        nom: el("fParent").value.trim() || parentActuel.nom || "—",
        tel: el("fTel").value.trim() || parentActuel.tel || "—",
        email: el("fEmail").value.trim() || parentActuel.email || "—"
      }
    };
    var bouton = document.getElementById("btnSaveEleve");
    bouton.disabled = true;
    bouton.textContent = "Enregistrement…";

    function terminer() {
      bouton.disabled = false;
      bouton.textContent = "💾 Enregistrer";
    }
    function reussite(message) {
      SM.closeAllModals();
      SM.toast(message, "success");
      actualiser();
      terminer();
    }
    function echec(err) {
      SM.toast("Enregistrement impossible : " + (err && err.detail ? err.detail : "erreur réseau."), "error");
      terminer();
    }

    if (editId) {
      API.majEleve(editId, d).then(function (rep) {
        var pos = eleves.findIndex(function (x) { return x.id === editId; });
        if (pos !== -1) eleves[pos] = normaliserEleve(rep);
        reussite("Élève " + editId + " modifié avec succès ✅");
      }, echec);
    } else {
      API.creerEleve(d).then(function (rep) {
        eleves.push(normaliserEleve(rep));
        reussite("Élève " + rep.id + " ajouté avec succès ✅");
      }, echec);
    }
  });

  /* ---------- Suppression ---------- */
  document.getElementById("btnConfirmDel").addEventListener("click", function () {
    if (!deleteId) return;
    var bouton = document.getElementById("btnConfirmDel");
    bouton.disabled = true;
    var id = deleteId;
    API.supprimerEleve(id).then(function () {
      var pos = eleves.findIndex(function (x) { return x.id === id; });
      if (pos !== -1) eleves.splice(pos, 1);
      SM.toast("Élève " + id + " supprimé.", "warning");
      deleteId = null;
      SM.closeAllModals();
      actualiser();
    }).catch(function (err) {
      SM.toast("Suppression impossible : " + (err && err.detail ? err.detail : "erreur réseau."), "error");
    }).then(function () {
      bouton.disabled = false;
    });
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
