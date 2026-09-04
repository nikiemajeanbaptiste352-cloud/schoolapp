/* ============================================================
   SchoolManager — Matières
   ============================================================ */

(function () {
  "use strict";

  var SM = window.SM;
  var SD = window.SD;

  function el(id) { return document.getElementById(id); }

  /* Classes qui suivent une matière donnée */
  function classesDeMatiere(matId) {
    return SD.classes.filter(function (c) {
      return SD.matieresDeClasse(c.id).some(function (m) { return m.id === matId; });
    });
  }

  /* ---------- Compteurs ---------- */
  var coefTotal = SD.matieres.reduce(function (s, m) { return s + m.coef; }, 0);
  el("coefTotal").textContent = coefTotal;
  el("miniCounts").innerHTML =
    '<div class="mini-stat"><div class="v">' + SD.matieres.length + '</div><div class="l">Matières</div></div>' +
    '<div class="mini-stat"><div class="v">' + coefTotal + '</div><div class="l">Coef. total</div></div>' +
    '<div class="mini-stat"><div class="v">' + SD.classes.length + '</div><div class="l">Classes</div></div>' +
    '<div class="mini-stat"><div class="v">' + SD.enseignants.length + '</div><div class="l">Enseignants</div></div>';

  /* ---------- Rendu ---------- */
  el("tableBody").innerHTML = SD.matieres.map(function (m) {
    var profs = SD.enseignants.filter(function (e) { return e.matiere === m.id; });
    var classes = classesDeMatiere(m.id);
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
      "</tr>"
    );
  }).join("");
})();
