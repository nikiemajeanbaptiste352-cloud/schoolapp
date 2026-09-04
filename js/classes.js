/* ============================================================
   SchoolManager — Classes (grille de cartes)
   ============================================================ */

(function () {
  "use strict";

  var SM = window.SM;
  var SD = window.SD;

  function el(id) { return document.getElementById(id); }

  /* ---------- Compteurs généraux ---------- */
  var totalEleves = SD.eleves.length;
  var nbCollege = SD.classes.filter(function (c) { return c.cycle === "Collège"; }).length;
  var nbLycee = SD.classes.filter(function (c) { return c.cycle === "Lycée"; }).length;
  el("miniCounts").innerHTML =
    '<div class="mini-stat"><div class="v">' + SD.classes.length + '</div><div class="l">Classes</div></div>' +
    '<div class="mini-stat"><div class="v">' + nbCollege + '</div><div class="l">Collège</div></div>' +
    '<div class="mini-stat"><div class="v">' + nbLycee + '</div><div class="l">Lycée</div></div>' +
    '<div class="mini-stat"><div class="v">' + totalEleves + '</div><div class="l">Élèves</div></div>';
  el("countBadge").textContent = "Année scolaire " + SD.ecole.annee;

  /* ---------- Rendu des cartes ---------- */
  function render() {
    el("classesGrid").innerHTML = SD.classes.map(function (c) {
      var effectif = SD.elevesDeClasse(c.id).length;
      var principal = SD.getEnseignant(c.principal);
      var nbM = SD.matieresDeClasse(c.id).length;
      var badgeCycle = c.cycle === "Lycée"
        ? '<span class="badge badge-warning">Lycée</span>'
        : '<span class="badge badge-info">Collège</span>';
      return (
        '<div class="card class-card">' +
        '  <div class="c-top">' +
        "    <div>" +
        '      <div class="c-name">' + SM.escapeHtml(c.nom) + "</div>" +
        '      <div class="text-sm text-muted mt-4">Salle ' + SM.escapeHtml(c.salle) + "</div>" +
        "    </div>" +
        "    " + badgeCycle +
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
        '    <a class="btn btn-outline btn-sm" href="grades.html?classe=' + c.id + '" title="Saisir les notes">📝 Notes</a>' +
        '    <a class="btn btn-ghost btn-sm" href="timetable.html?classe=' + c.id + '" title="Emploi du temps">📅 EDT</a>' +
        "  </div>" +
        "</div>"
      );
    }).join("");
  }
  render();

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

  el("classesGrid").addEventListener("click", function (e) {
    var btn = e.target.closest("[data-detail]");
    if (btn) ouvrirDetail(btn.getAttribute("data-detail"));
  });
})();
