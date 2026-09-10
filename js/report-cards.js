/* ============================================================
   SchoolManager — Bulletins scolaires (imprimable)
   ============================================================ */

(function () {
  "use strict";

  var SM = window.SM;
  var SD = window.SD;

  function el(id) { return document.getElementById(id); }
  var params = new URLSearchParams(window.location.search);

  /* ---------- Remplissage du sélecteur d'élèves ---------- */
  var selEleve = el("selEleve");
  SD.eleves.slice().sort(function (a, b) {
    return (a.nom + a.prenom).localeCompare(b.nom + b.prenom, "fr");
  }).forEach(function (e) {
    var o = document.createElement("option");
    o.value = e.id;
    var c = SD.getClasse(e.classe);
    o.textContent = e.nom + " " + e.prenom + " — " + (c ? c.nom : e.classe) + " (" + e.id + ")";
    selEleve.appendChild(o);
  });
  if (params.get("eleve")) selEleve.value = params.get("eleve");

  function virgule(n) { return n.toFixed(2).replace(".", ","); }

  /* ---------- Génération du bulletin ---------- */
  function generer() {
    var eleve = SD.getEleve(selEleve.value);
    if (!eleve) { el("bulletin").innerHTML = ""; return; }
    var classe = SD.getClasse(eleve.classe);
    var nomC = eleve.nom + " " + eleve.prenom;
    document.title = "Bulletin — " + nomC;

    var m = SD.moyennesEleve(eleve.id);
    var rang = SD.rangEleve(eleve.id);
    var app = SD.appreciation(m.generale);

    var html = "";

    /* En-tête de l'école */
    html +=
      '<div class="bulletin-head">' +
      '  <img class="logo" src="../assets/logo.svg" alt="Logo">' +
      '  <div style="flex:1">' +
      '    <div class="school-name">' + SM.escapeHtml(SD.ecole.nom) + "</div>" +
      '    <div class="school-sub">' + SM.escapeHtml(SD.ecole.adresse) + " · Tél : " + SM.escapeHtml(SD.ecole.telephone) + " · " + SM.escapeHtml(SD.ecole.email) + "</div>" +
      "  </div>" +
      '  <div style="text-align:right"><div class="school-sub">Année scolaire</div><div class="fw-700">' + SM.escapeHtml(SD.ecole.annee) + "</div></div>" +
      "</div>" +
      '<div class="bulletin-title">📄 BULLETIN SCOLAIRE</div>';

    /* Informations élève */
    html +=
      '<div class="bulletin-info">' +
      '  <div><div class="school-sub">Élève</div><div class="fw-700">' + SM.escapeHtml(nomC) + "</div></div>" +
      '  <div><div class="school-sub">Matricule / Classe</div><div class="fw-700">' + SM.escapeHtml(eleve.id) + " · " + SM.escapeHtml(classe ? classe.nom : eleve.classe) + "</div></div>" +
      '  <div><div class="school-sub">Période</div><div class="fw-700">1er trimestre</div></div>' +
      "</div>";

    /* Tableau des matières */
    if (!m.parMatiere.length) {
      html += '<div class="alert alert-warning">Aucune note n\'est encore enregistrée pour cet élève.</div>';
    } else {
      var rows = m.parMatiere.map(function (p, i) {
        var mention = SD.appreciation(p.moyenne).mention;
        return (
          "<tr>" +
          "<td>" + (i + 1) + "</td>" +
          "<td class='fw-600'>" + p.icone + " " + SM.escapeHtml(p.matiere) + "</td>" +
          '<td style="text-align:center">' + p.coef + "</td>" +
          '<td style="text-align:center" class="fw-600">' + virgule(p.moyenne) + "</td>" +
          "<td>" + SM.escapeHtml(mention) + "</td>" +
          "</tr>"
        );
      }).join("");

      html +=
        '<div class="bulletin-tbl"><table>' +
        "<thead><tr>" +
        '<th style="width:40px">N°</th><th>Matière</th>' +
        '<th style="width:70px;text-align:center">Coef.</th>' +
        '<th style="width:110px;text-align:center">Moyenne / 20</th>' +
        "<th>Appréciation</th>" +
        "</tr></thead><tbody>" +
        rows +
        '<tr class="total-row"><td colspan="2">MOYENNE GÉNÉRALE</td>' +
        '<td style="text-align:center">' + m.totalCoef + "</td>" +
        '<td style="text-align:center">' + virgule(m.generale) + " / 20</td>" +
        "<td>" + SM.escapeHtml(app.mention) + "</td>" +
        "</tr>" +
        "</tbody></table></div>";

      html +=
        '<div class="bulletin-info" style="margin-top:16px">' +
        '  <div><div class="school-sub">Rang</div><div class="fw-700">' + (rang ? rang.rang + "ᵉ sur " + rang.total : "—") + "</div></div>" +
        '  <div><div class="school-sub">Mention</div><div class="fw-700">' + SM.escapeHtml(app.mention) + "</div></div>" +
        '  <div><div class="school-sub">Total coef.</div><div class="fw-700">' + m.totalCoef + "</div></div>" +
        "</div>";

      html +=
        '<div class="bulletin-appr">' +
        '  <div class="school-sub">💬 Appréciation du conseil de classe</div>' +
        "  <p class='fw-600' style='margin:6px 0 0'>« " + SM.escapeHtml(app.texte) + " »</p>" +
        "</div>";
    }

    html +=
      '<div class="bulletin-sign">' +
      '  <div style="text-align:center"><div class="fw-700">' + SM.escapeHtml(SD.ecole.sigle) + "</div><div>Le Directeur</div></div>" +
      '  <div style="text-align:center"><div class="fw-700">Le Professeur principal</div><div>' + (classe && classe.principal
        ? SM.escapeHtml((SD.getEnseignant(classe.principal) || {}).prenom || "") + " " + SM.escapeHtml((SD.getEnseignant(classe.principal) || {}).nom || "")
        : "") + "</div></div>" +
      '  <div style="text-align:center"><div class="fw-700">Les Parents</div><div>Signature</div></div>' +
      "</div>";

    el("bulletin").innerHTML = html;
  }

  selEleve.addEventListener("change", generer);
  el("btnPrint").addEventListener("click", function () {
    window.print();
  });

  generer();
})();
