/* ============================================================
   SchoolManager — Classes (grille de cartes + gestion admin)
   ============================================================ */

(function () {
  "use strict";

  var SM = window.SM;
  var SD = window.SD;

  function el(id) { return document.getElementById(id); }

  // Droit d'écriture décidé par le serveur (capacités de GET /api/v1/etat),
  // et non plus par le rôle mémorisé dans le navigateur : ce dernier est
  // modifiable à la main et seule l'API reste juge, mais l'interface doit
  // refléter la même règle (voir backend/app/services/perimetre.py).
  var estAdmin = SM.peut("classes.ecrire");
  var role = SM.roleCourant();
  var estProf = role === "Professeur";
  var peutSaisirNotes = SM.peut("notes.ecrire");
  // Un lien n'est proposé que si la page cible fait partie des pages du rôle
  // (ex. le surveillant n'ouvre pas la saisie des notes) : voir
  // perimetre.PAGES_PAR_ROLE côté serveur.
  var peutNotes = SM.pageAutorisee("grades", role);
  var peutEdt = SM.pageAutorisee("timetable", role);
  // Fiche enseignant du compte connecté : sert uniquement à signaler « mes
  // classes » dans les compteurs, sans retirer la vue complète accordée par
  // le serveur (les professeurs et surveillants voient toutes les classes).
  var maFiche = estProf ? SM.monEnseignant(SD) : null;
  var mesClasses = maFiche ? maFiche.classes : [];
  var editId = null;   // code de la classe en édition (null = création)
  var deleteId = null;

  /* ---------- Sélecteur professeur principal ---------- */
  function remplirPrincipaux(selection) {
    var sel = el("classePrincipal");
    sel.innerHTML = '<option value="">— Aucun</option>';
    SD.enseignants.forEach(function (e) {
      var o = document.createElement("option");
      o.value = e.id;
      o.textContent = e.id + " — " + e.prenom + " " + e.nom;
      sel.appendChild(o);
    });
    sel.value = selection || "";
  }

  /* ---------- Compteurs généraux ---------- */
  function compteurs() {
    var nbCollege = SD.classes.filter(function (c) { return c.cycle === "Collège"; }).length;
    var nbLycee = SD.classes.filter(function (c) { return c.cycle === "Lycée"; }).length;
    if (estProf && maFiche) {
      // Le professeur garde la vue complète, mais son propre volume de service
      // est mis en avant : c'est ce qu'il vient chercher ici.
      el("miniCounts").innerHTML =
        '<div class="mini-stat"><div class="v">' + mesClasses.length + '</div><div class="l">Mes classes</div></div>' +
        '<div class="mini-stat"><div class="v">' + SD.classes.length + '</div><div class="l">Classes</div></div>' +
        '<div class="mini-stat"><div class="v">' + nbCollege + '</div><div class="l">Collège</div></div>' +
        '<div class="mini-stat"><div class="v">' + nbLycee + '</div><div class="l">Lycée</div></div>';
      el("countBadge").textContent = "Année scolaire " + (SD.ecole && SD.ecole.annee ? SD.ecole.annee : "—");
      return;
    }
    el("miniCounts").innerHTML =
      '<div class="mini-stat"><div class="v">' + SD.classes.length + '</div><div class="l">Classes</div></div>' +
      '<div class="mini-stat"><div class="v">' + nbCollege + '</div><div class="l">Collège</div></div>' +
      '<div class="mini-stat"><div class="v">' + nbLycee + '</div><div class="l">Lycée</div></div>' +
      '<div class="mini-stat"><div class="v">' + SD.eleves.length + '</div><div class="l">Élèves</div></div>';
    el("countBadge").textContent = "Année scolaire " + (SD.ecole && SD.ecole.annee ? SD.ecole.annee : "—");
  }
  compteurs();

  /* ---------- Rendu des cartes ---------- */
  function render() {
    el("classesGrid").innerHTML = SD.classes.map(function (c) {
      var effectif = SD.elevesDeClasse(c.id).length;
      var principal = SD.getEnseignant(c.principal);
      var nbM = SD.matieresDeClasse(c.id).length;
      var mienne = mesClasses.indexOf(c.id) !== -1;
      var badgeCycle = c.cycle === "Lycée"
        ? '<span class="badge badge-warning">Lycée</span>'
        : '<span class="badge badge-info">Collège</span>';
      var badgeMienne = mienne ? '<span class="badge badge-success">Ma classe</span>' : "";
      var btnAdmin = estAdmin
        ? '<button class="btn-icon primary-h" title="Modifier" data-edit="' + c.id + '">✏️</button>' +
          '<button class="btn-icon danger" title="Supprimer" data-del="' + c.id + '">🗑️</button>'
        : "";
      var lienNotes = peutNotes
        ? '<a class="btn btn-outline btn-sm" href="grades.html?classe=' + c.id + '" title="' +
          (peutSaisirNotes ? "Saisir les notes" : "Consulter les notes") + '">📝 Notes</a>'
        : "";
      var lienEdt = peutEdt
        ? '<a class="btn btn-ghost btn-sm" href="timetable.html?classe=' + c.id + '" title="Emploi du temps">📅 EDT</a>'
        : "";
      return (
        '<div class="card class-card"' + (mienne ? ' style="border-color:var(--success)"' : "") + ">" +
        '  <div class="c-top">' +
        "    <div>" +
        '      <div class="c-name">' + SM.escapeHtml(c.nom) + "</div>" +
        '      <div class="text-sm text-muted mt-4">Salle ' + SM.escapeHtml(c.salle || "—") + "</div>" +
        "    </div>" +
        "    " + badgeMienne + badgeCycle +
        "  </div>" +
        '  <div class="c-counts">' +
        '    <span class="chip">👨‍🎓 ' + effectif + " élève" + (effectif > 1 ? "s" : "") + "</span>" +
        '    <span class="chip-plain">📚 ' + nbM + " matières</span>" +
        "  </div>" +
        '  <div class="flex" style="gap:10px;align-items:center">' +
        "    " + SM.avatarHTML(principal ? principal.nom + " " + principal.prenom : "?", "sm") +
        '    <div class="text-sm"><div class="fw-600">' + (principal ? SM.escapeHtml(principal.nom + " " + principal.prenom) : "À nommer") + "</div>" +
        '      <div class="text-muted">Professeur principal</div></div>' +
        "  </div>" +
        '  <div class="flex" style="gap:8px;flex-wrap:wrap;margin-top:4px">' +
        '    <button class="btn btn-outline btn-sm" data-detail="' + c.id + '">👥 Détails</button>' +
        lienNotes +
        lienEdt +
        btnAdmin +
        "  </div>" +
        "</div>"
      );
    }).join("");
    if (!SD.classes.length) {
      el("classesGrid").innerHTML =
        '<div class="empty-state" style="grid-column:1/-1"><div class="e-ico">🏫</div><h4>Aucune classe</h4>' +
        "<p>Aucune classe n'est rattachée à cet établissement.</p></div>";
    }
  }
  render();

  // Bouton « Ajouter » visible pour l'administrateur uniquement
  if (estAdmin && el("btnAddClasse")) el("btnAddClasse").style.display = "";

  /* ---------- Modale détails ---------- */
  function ouvrirDetail(classeId) {
    var c = SD.getClasse(classeId);
    if (!c) return;
    var principal = SD.getEnseignant(c.principal);
    var listeEleves = SD.elevesDeClasse(c.id);
    var matieres = SD.matieresDeClasse(c.id);
    el("modalTitle").textContent = "🏫 Classe " + c.nom;

    var html =
      '<div class="info-grid mb-16" style="grid-template-columns:repeat(auto-fit,minmax(140px,1fr))">' +
      '  <div class="info-cell"><div class="k">Cycle</div><div class="v">' + SM.escapeHtml(c.cycle) + "</div></div>" +
      '  <div class="info-cell"><div class="k">Salle</div><div class="v">' + SM.escapeHtml(c.salle) + "</div></div>" +
      '  <div class="info-cell"><div class="k">Effectif</div><div class="v">' + listeEleves.length + " élèves</div></div>" +
      '  <div class="info-cell"><div class="k">Matières</div><div class="v">' + matieres.length + "</div></div>" +
      '  <div class="info-cell"><div class="k">Prof. principal</div><div class="v">' + (principal ? SM.escapeHtml(principal.nom + " " + principal.prenom) : "À nommer") + "</div></div>" +
      "</div>" +
      '<div class="notes-grid">' +
      "  <div>" +
      '    <h3 class="mb-8" style="font-size:14px">📚 Matières enseignées</h3>' +
      '    <div class="table-wrap"><table class="data" style="min-width:320px"><thead><tr><th>Matière</th><th class="text-center">Coef.</th><th>Enseignant</th></tr></thead><tbody>' +
      matieres.map(function (m) {
        var prof = SD.enseignants.find(function (e) { return e.matiere === m.id && e.classes.indexOf(c.id) !== -1; }) ||
                   SD.enseignants.find(function (e) { return e.matiere === m.id; });
        return "<tr><td><div class='flex-center' style='justify-content:flex-start'>" + m.icone + " <span class='fw-600'>" + SM.escapeHtml(m.nom) +
          "</span></div></td><td class='text-center'>" + m.coef + "</td><td>" +
          (prof ? SM.escapeHtml(prof.prenom + " " + prof.nom) : '<span class="text-muted">—</span>') + "</td></tr>";
      }).join("") +
      "</tbody></table></div>" +
      "  </div>" +
      "  <div>" +
      '    <h3 class="mb-8" style="font-size:14px">👨‍🎓 Liste des élèves</h3>' +
      (listeEleves.length
        ? '<div class="table-wrap"><table class="data" style="min-width:280px"><thead><tr><th>Matricule</th><th>Élève</th><th>Statut</th></tr></thead><tbody>' +
          listeEleves.map(function (e) {
            return "<tr><td class='fw-600'>" + SM.escapeHtml(e.id) + '</td><td><a href="student-profile.html?id=' + e.id + '">' +
              SM.escapeHtml(e.nom + " " + e.prenom) + "</a></td><td>" + SM.badgeStatut(e.statut) + "</td></tr>";
          }).join("") +
          "</tbody></table></div>"
        : '<div class="empty-state" style="padding:20px"><div class="e-ico">🪑</div><h4>Aucun élève</h4></div>') +
      "  </div>" +
      "</div>";

    el("modalBody").innerHTML = html;
    SM.openModal("modalClasse");
  }

  /* ---------- Actions des cartes ---------- */
  el("classesGrid").addEventListener("click", function (e) {
    var btnDetail = e.target.closest("[data-detail]");
    if (btnDetail) { ouvrirDetail(btnDetail.getAttribute("data-detail")); return; }
    if (!estAdmin) return;
    var btn = e.target.closest("[data-edit], [data-del]");
    if (!btn) return;
    var id = btn.getAttribute("data-edit") || btn.getAttribute("data-del");
    if (btn.hasAttribute("data-edit")) {
      ouvrirEdition(id);
    } else {
      deleteId = id;
      var c = SD.getClasse(id);
      var nb = SD.elevesDeClasse(id).length;
      el("delClasseText").innerHTML =
        "La classe <b>" + SM.escapeHtml(c ? c.nom : id) + "</b> (" + id + ") sera supprimée." +
        (nb
          ? ' <div class="mt-8 text-sm" style="color:var(--danger-text)">⚠️ ' + nb + " élève(s) inscrit(s) : la suppression sera refusée tant que la classe n'est pas vide.</div>"
          : "");
      SM.openModal("modalDelClasse");
    }
  });

  /* ---------- Formulaire ajout / modification ---------- */
  function clearErreurs() {
    document.querySelectorAll(".field-error.show").forEach(function (x) { x.classList.remove("show"); });
    document.querySelectorAll(".input.invalid").forEach(function (x) { x.classList.remove("invalid"); });
  }
  function cyclePourCode(code) {
    // Codes type lycée : 2nde, 1ère, Terminale (commencent par 1, 2 ou T)
    return /^[12T]/.test((code || "").trim()) ? "Lycée" : "Collège";
  }
  function resetForm() {
    editId = null;
    el("classeModalTitle").textContent = "➕ Ajouter une classe";
    el("classeCode").value = "";
    el("classeCode").readOnly = false;
    el("classeNom").value = "";
    el("classeCycle").value = "Collège";
    el("classeSalle").value = "";
    remplirPrincipaux("");
    clearErreurs();
    SM.openModal("modalClasseEdit");
  }
  function ouvrirEdition(id) {
    var c = SD.getClasse(id);
    if (!c) return;
    editId = id;
    el("classeModalTitle").textContent = "✏️ Modifier la classe " + c.id;
    el("classeCode").value = c.id;
    el("classeCode").readOnly = true; // le code est la clé primaire : non modifiable
    el("classeNom").value = c.nom;
    el("classeCycle").value = c.cycle;
    el("classeSalle").value = c.salle || "";
    remplirPrincipaux(c.principal || "");
    clearErreurs();
    SM.openModal("modalClasseEdit");
  }

  var btnAdd = el("btnAddClasse");
  if (estAdmin && btnAdd) {
    btnAdd.addEventListener("click", resetForm);
    el("classeCode").addEventListener("input", function () {
      if (!editId && el("classeCycle").value !== cyclePourCode(el("classeCode").value)) {
        el("classeCycle").value = cyclePourCode(el("classeCode").value);
      }
    });
  }

  /* ---------- Enregistrement ---------- */
  el("btnSaveClasse").addEventListener("click", function () {
    clearErreurs();
    var code = el("classeCode").value.trim().toUpperCase();
    var ok = true;
    if (!code) {
      el("classeCode").classList.add("invalid");
      el("errClasseCode").classList.add("show");
      ok = false;
    } else if (!/^[A-Z0-9]{1,6}$/.test(code)) {
      el("classeCode").classList.add("invalid");
      el("errClasseCode").textContent = "Code invalide : lettres et chiffres uniquement (ex. 6C, TA).";
      el("errClasseCode").classList.add("show");
      ok = false;
    } else {
      el("errClasseCode").textContent = "Le code est obligatoire (ex. 6C, 3C, TA…).";
    }
    if (!ok) { SM.toast("Veuillez corriger le formulaire.", "error"); return; }

    var d = {
      id: code,
      nom: el("classeNom").value.trim() || code,
      cycle: el("classeCycle").value,
      salle: el("classeSalle").value.trim() || "—",
      principal: el("classePrincipal").value || null
    };
    var bouton = el("btnSaveClasse");
    bouton.disabled = true;
    bouton.textContent = "Enregistrement…";

    function terminer() { bouton.disabled = false; bouton.textContent = "💾 Enregistrer"; }
    function reussite(message) {
      SM.closeModal("modalClasseEdit");
      SM.toast(message, "success");
      compteurs();
      render();
    }
    function echec(err) {
      SM.toast("Enregistrement impossible : " + (err && err.detail ? err.detail : "erreur réseau."), "error");
      terminer();
    }

    if (editId) {
      API.majClasse(editId, d).then(function (rep) {
        var idx = SD.classes.findIndex(function (x) { return x.id === editId; });
        if (idx !== -1) SD.classes[idx] = rep; else SD.classes.push(rep);
        reussite("Classe " + editId + " modifiée ✅");
        terminer();
      }, echec);
    } else {
      API.creerClasse(d).then(function (rep) {
        SD.classes.push(rep);
        reussite("Classe " + rep.id + " ajoutée ✅");
        terminer();
      }, echec);
    }
  });

  /* ---------- Suppression ---------- */
  el("btnConfirmDelClasse").addEventListener("click", function () {
    if (!deleteId) return;
    var bouton = el("btnConfirmDelClasse");
    bouton.disabled = true;
    var id = deleteId;
    API.supprimerClasse(id).then(function () {
      var idx = SD.classes.findIndex(function (x) { return x.id === id; });
      if (idx !== -1) SD.classes.splice(idx, 1);
      SM.toast("Classe " + id + " supprimée.", "warning");
      SM.closeModal("modalDelClasse");
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
