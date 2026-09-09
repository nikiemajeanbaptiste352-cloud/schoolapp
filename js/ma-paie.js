/* ============================================================
   SchoolManager — 💵 Ma rémunération (enseignant)
   Consultation seule des fiches de paie mensuelles générées par
   la direction : période, heures signées, taux horaire, montant,
   statut (en attente / payée). Fiche imprimable.
   ============================================================ */

(function () {
  "use strict";

  var SM = window.SM;
  var API = window.API;

  var sess = SM.getSession();
  if (!sess || sess.role !== "Professeur") {
    window.location.replace("../index.html");
    return;
  }

  function el(id) { return document.getElementById(id); }

  var MOIS_NOMS = ["janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre"];
  function libelleMois(mois) {
    if (!mois || mois.length !== 7) return mois || "";
    var annee = mois.slice(0, 4);
    var m = parseInt(mois.slice(5, 7), 10) - 1;
    var nom = MOIS_NOMS[m] ? MOIS_NOMS[m] : "";
    return nom ? nom.charAt(0).toUpperCase() + nom.slice(1) + " " + annee : mois;
  }
  function fmtDuree(h) {
    if (h === null || h === undefined || isNaN(h)) return "—";
    var total = Math.round(Number(h) * 60);
    var hh = Math.floor(total / 60);
    var mm = total % 60;
    return hh + " h " + ("0" + mm).slice(-2);
  }
  function fmtStatut(s) {
    if (s.statut === "payee") return { texte: "Payée", cls: "badge-success", ico: "✅" };
    return { texte: "En attente", cls: "badge-warning", ico: "⏳" };
  }
  function erreur(e) {
    var msg = (e && e.detail) ? e.detail : (e && e.message) ? e.message : "Erreur inconnue.";
    SM.toast(String(msg), "error");
  }

  /* ---------- État ---------- */
  var fiches = [];
  var devise = "FCFA";

  function miniStats() {
    var enAttente = 0, payees = 0, heures = 0, totalPaye = 0;
    fiches.forEach(function (f) {
      heures += Number(f.heures || 0);
      if (f.statut === "payee") { payees++; totalPaye += Number(f.brut || 0); }
      else { enAttente++; }
    });
    el("miniStats").innerHTML =
      '<div class="stat-card"><div class="stat-ico orange">⏳</div><div>' +
      '<div class="stat-value">' + enAttente + '</div><div class="stat-label">Fiche' + (enAttente > 1 ? "s" : "") + " en attente</div></div></div>" +
      '<div class="stat-card"><div class="stat-ico green">✅</div><div>' +
      '<div class="stat-value">' + payees + '</div><div class="stat-label">Fiche' + (payees > 1 ? "s" : "") + " payée" + (payees > 1 ? "s" : "") + "</div></div></div>" +
      '<div class="stat-card"><div class="stat-ico blue">🕐</div><div>' +
      '<div class="stat-value">' + fmtDuree(heures) + '</div><div class="stat-label">Heures facturées</div></div></div>' +
      '<div class="stat-card"><div class="stat-ico purple">💰</div><div>' +
      '<div class="stat-value" style="font-size:22px">' + SM.formatFCFA(totalPaye) + '</div><div class="stat-label">Total déjà réglé</div></div></div>';
  }

  function carteFiche(f) {
    var st = fmtStatut(f);
    var dates = "";
    if (f.statut === "payee" && f.payeeLe) {
      dates = "<div class='text-muted' style='font-size:13px;margin-top:2px'>Payé le " + SM.escapeHtml(String(f.payeeLe).replace(" ", " à ")) + "</div>";
    }
    return (
      '<div class="card">' +
      '  <div class="card-head">' +
      '    <h3>📄 ' + SM.escapeHtml(libelleMois(f.mois)) + "</h3>" +
      '    <div style="text-align:right">' + SM.badgeStatut(st.texte) + dates + "</div>" +
      "  </div>" +
      '  <div class="card-pad">' +
      '    <div class="info-grid">' +
      '      <div class="info-cell"><div class="k">Enseignant(e)</div><div class="v">' + SM.escapeHtml(f.enseignantNom) + "</div></div>" +
      '      <div class="info-cell"><div class="k">Matière</div><div class="v">' + SM.escapeHtml(f.matiereNom || "—") + "</div></div>" +
      '      <div class="info-cell"><div class="k">Période</div><div class="v">' + SM.escapeHtml(libelleMois(f.mois)) + "</div></div>" +
      '      <div class="info-cell"><div class="k">Heures signées</div><div class="v">' + fmtDuree(f.heures) + "</div></div>" +
      '      <div class="info-cell"><div class="k">Taux horaire</div><div class="v">' + SM.formatFCFA(f.tauxHoraire) + "</div></div>" +
      '      <div class="info-cell"><div class="k">Montant brut (= net)</div><div class="v" style="color:var(--success-text);font-size:18px">' + SM.formatFCFA(f.brut) + "</div></div>" +
      "    </div>" +
      '    <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;margin-top:18px;flex-wrap:wrap">' +
      '      <span class="text-muted" style="font-size:13px">Aucune retenue : rémunération à la vacation.</span>' +
      '      <button class="btn btn-outline btn-sm" data-print="' + f.id + '">🖨️ Imprimer la fiche</button>' +
      "    </div>" +
      "  </div>" +
      "</div>"
    );
  }

  function render() {
    var zone = el("ficheList");
    miniStats();
    if (!fiches.length) {
      zone.innerHTML =
        '<div class="card"><div class="card-pad" style="text-align:center;padding:48px 24px">' +
        '<div style="font-size:44px;margin-bottom:12px">💵</div>' +
        "<h3 style='margin-bottom:6px'>Aucune fiche de paie pour le moment</h3>" +
        "<p class='text-muted'>La direction génère votre fiche chaque mois à partir de vos séances signées dans « Ma présence ».</p>" +
        "</div></div>";
      return;
    }
    zone.innerHTML = fiches.map(carteFiche).join("");
  }

  function charger() {
    return API.mesFiches()
      .then(function (d) {
        fiches = d.fiches || [];
        devise = d.devise || "FCFA";
        render();
      })
      .catch(erreur);
  }

  /* ---------- Impression de la fiche ---------- */
  function ficheParId(id) {
    for (var i = 0; i < fiches.length; i++) {
      if (String(fiches[i].id) === String(id)) return fiches[i];
    }
    return null;
  }

  function construireFiche(id) {
    var f = ficheParId(id);
    if (!f) return;
    var st = fmtStatut(f);
    var ecole = (window.SD && window.SD.ecole) || {};
    var montant = SM.formatFCFA(f.brut);
    var taux = SM.formatFCFA(f.tauxHoraire);

    el("fichePrint").innerHTML =
      '<div class="print-area">' +
      '<div class="bulletin">' +
      '  <div class="bulletin-head">' +
      '    <img class="logo" src="../assets/logo.svg" alt="Logo">' +
      "    <div>" +
      '      <div class="school-name">' + SM.escapeHtml(ecole.nom || "Établissement") + "</div>" +
      '      <div class="school-sub">' + (ecole.annee ? "Année scolaire " + SM.escapeHtml(ecole.annee) + " · " : "") + "Rémunération des enseignants — vacation</div>" +
      "    </div>" +
      "  </div>" +
      '  <div class="bulletin-title">FICHE DE PAIE — ' + SM.escapeHtml(libelleMois(f.mois).toUpperCase()) + "</div>" +
      '  <div class="bulletin-info">' +
      '    <div><span class="text-muted">Enseignant(e)</span><br><strong>' + SM.escapeHtml(f.enseignantNom) + "</strong></div>" +
      '    <div><span class="text-muted">Matière</span><br><strong>' + SM.escapeHtml(f.matiereNom || "—") + "</strong></div>" +
      '    <div><span class="text-muted">Statut</span><br><strong>' + SM.escapeHtml(st.texte) + (f.payeeLe ? " — le " + SM.escapeHtml(String(f.payeeLe).split(" ")[0]) : "") + "</strong></div>" +
      "  </div>" +
      "  <table>" +
      "    <thead><tr><th style='width:60%'>Désignation</th><th style='text-align:right'>Détail</th><th style='text-align:right'>Montant</th></tr></thead>" +
      "    <tbody>" +
      '      <tr><td>Rémunération à la vacation — heures signées (' + SM.escapeHtml(libelleMois(f.mois)) + ")</td>" +
      '        <td style="text-align:right">' + fmtDuree(f.heures) + " × " + SM.escapeHtml(taux) + "/h</td>" +
      '        <td style="text-align:right">' + SM.escapeHtml(montant) + "</td></tr>" +
      "    </tbody>" +
      "    <tfoot>" +
      '      <tr class="total-row"><td>Montant brut</td><td></td><td style="text-align:right">' + SM.escapeHtml(montant) + "</td></tr>" +
      '      <tr class="total-row"><td>Retenues</td><td></td><td style="text-align:right">0 ' + SM.escapeHtml(devise) + '</td></tr>' +
      '      <tr class="total-row"><td>Net à payer</td><td></td><td style="text-align:right">' + SM.escapeHtml(montant) + "</td></tr>" +
      "    </tfoot>" +
      "  </table>" +
      '  <div class="bulletin-sign">' +
      '    <div>L’enseignant(e)<br>' + SM.escapeHtml(f.enseignantNom) + '<br><span class="text-muted">Signature : ______________________</span></div>' +
      '    <div style="text-align:right">La direction<br><span class="text-muted">Cachet et signature : ______________________</span></div>' +
      "  </div>" +
      "</div></div>";
    window.print();
  }

  /* ---------- Événements ---------- */
  el("ficheList").addEventListener("click", function (e) {
    var b = e.target.closest("[data-print]");
    if (b) construireFiche(b.getAttribute("data-print"));
  });

  charger();
})();
