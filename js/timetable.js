/* ============================================================
   SchoolManager — Emploi du temps
   ============================================================ */

(function () {
  "use strict";

  var SM = window.SM;
  var SD = window.SD;

  function el(id) { return document.getElementById(id); }
  var params = new URLSearchParams(window.location.search);

  /* ---------- Sélecteur de classe ---------- */
  var selClasse = el("selClasse");
  SD.classes.forEach(function (c) {
    var o = document.createElement("option");
    o.value = c.id;
    o.textContent = c.nom + " — " + c.cycle;
    selClasse.appendChild(o);
  });
  if (params.get("classe")) selClasse.value = params.get("classe");

  /* ---------- Rendu ---------- */
  function couleurMatiere(matId) {
    var matieres = SD.matieresDeClasse(selClasse.value);
    var idx = matieres.findIndex(function (m) { return m.id === matId; });
    return "slot-color-" + (idx === -1 ? 0 : idx % 8);
  }

  function render() {
    var classeId = selClasse.value;
    var classe = SD.getClasse(classeId);
    var cours = SD.emploiDuTemps(classeId);
    var matieres = SD.matieresDeClasse(classeId);

    /* Légende */
    el("legend").innerHTML =
      '<span class="fw-600" style="margin-right:4px">🎨 Légende :</span>' +
      matieres.map(function (m, i) {
        return '<span class="chip" style="background:transparent;padding:4px 10px;border-radius:8px;' +
          'background:' + getBg(i) + '">' + m.icone + " " + SM.escapeHtml(m.nom) + "</span>";
      }).join("");

    /* En-tête colonnes */
    var html = "<thead><tr><th class='time-col'>Horaires</th>" +
      SD.JOURS.map(function (j) { return "<th>" + j + "</th>"; }).join("") + "</tr></thead><tbody>";

    /* Lignes par créneau */
    html += SD.CRENEAUX.map(function (cr, ci) {
      var cells = SD.JOURS.map(function (jour, jj) {
        var c = cours.find(function (x) { return x.creneau === ci && x.jour === jour; });
        if (!c) {
          var pause = ci === 2 && (jj === 2 || jj === 5);
          return '<td style="text-align:center"><div class="slot-empty">' + (pause ? "🕐 Activités libres" : "—") + "</div></td>";
        }
        var m = SD.getMatiere(c.matiereId);
        return (
          '<td><div class="slot ' + couleurMatiere(c.matiereId) + '">' +
          '  <div class="m">' + (m ? m.icone : "📘") + " " + SM.escapeHtml(c.matiere) + "</div>" +
          '  <div class="t">👨‍🏫 ' + SM.escapeHtml(c.enseignant) + "</div>" +
          '  <div class="t">🚪 ' + SM.escapeHtml(c.salle) + "</div>" +
          "</div></td>"
        );
      }).join("");
      return "<tr><td class='time-cell'>" + SM.escapeHtml(cr.label) + "</td>" + cells + "</tr>";
    }).join("") + "</tbody>";

    el("grille").innerHTML = html;
    el("grille").setAttribute("style", "");
    document.title = "Emploi du temps — " + (classe ? classe.nom : "") + " | SchoolManager";
  }

  function getBg(i) {
    var colors = ["#dbeafe", "#d1fae5", "#fef3c7", "#f3e8ff", "#ffe4e6", "#cffafe", "#e0f2fe", "#fde68a"];
    return colors[i % colors.length];
  }

  selClasse.addEventListener("change", render);
  render();
})();
