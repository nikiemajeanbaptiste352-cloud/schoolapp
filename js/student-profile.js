/* ============================================================
   SchoolManager — Fiche détaillée d'un élève
   ============================================================ */

(function () {
  "use strict";

  var SM = window.SM;
  var SD = window.SD;

  /* ---------- Identification de l'élève ---------- */
  var params = new URLSearchParams(window.location.search);
  var eleve = SD.getEleve(params.get("id")) || SD.getEleve("EL001");
  if (!eleve) {
    document.getElementById("profileHead").innerHTML = '<div class="alert alert-danger">Élève introuvable.</div>';
    return;
  }

  var classe = SD.getClasse(eleve.classe);
  var nomC = eleve.nom + " " + eleve.prenom;
  var rang = SD.rangEleve(eleve.id);
  document.title = nomC + " — Fiche élève";

  /* ---------- En-tête profil ---------- */
  document.getElementById("profileHead").innerHTML =
    SM.avatarHTML(nomC, "lg") +
    '<div><h2>' + SM.escapeHtml(eleve.nom) + " " + SM.escapeHtml(eleve.prenom) + "</h2>" +
    '  <div class="p-sub">Matricule ' + SM.escapeHtml(eleve.id) + " · Classe " + SM.escapeHtml(classe.nom) + "</div>" +
    '  <div class="flex mt-8" style="gap:8px">' + SM.badgeStatut(eleve.statut) +
    (rang ? ' <span class="badge badge-important">🏅 Rang ' + rang.rang + "/" + rang.total + " de la classe</span>" : "") + "</div>" +
    "</div>" +
    '<div class="profile-meta"><div style="text-align:right">' +
    '  <div class="text-sm" style="opacity:.75">Présence</div><div style="font-size:30px;font-weight:800">' + SD.tauxPresence(eleve.id) + "%</div></div></div>";

  /* ---------- Grille d'informations ---------- */
  var infos = [
    ["Matricule", eleve.id],
    ["Nom complet", nomC],
    ["Sexe", eleve.sexe === "M" ? "Masculin" : "Féminin"],
    ["Date de naissance", SM.fmtDate(eleve.naissance)],
    ["Classe", classe.nom],
    ["Cycle", classe.cycle],
    ["Inscription", SM.fmtDate(eleve.inscription)],
    ["Statut", eleve.statut]
  ];
  document.getElementById("infoGrid").innerHTML = infos.map(function (x) {
    return '<div class="info-cell"><div class="k">' + x[0] + '</div><div class="v">' + SM.escapeHtml(String(x[1])) + "</div></div>";
  }).join("");

  document.getElementById("btnBulletin").href = "report-cards.html?eleve=" + eleve.id;

  /* ---------- Navigation par onglets ---------- */
  var onglets = ["notes", "presences", "paiements", "bulletins", "parent"];
  document.getElementById("tabs").addEventListener("click", function (e) {
    var tab = e.target.closest(".tab");
    if (!tab) return;
    var cible = tab.getAttribute("data-tab");
    onglets.forEach(function (o) {
      document.querySelector('.tab[data-tab="' + o + '"]').classList.toggle("active", o === cible);
      document.getElementById("pane-" + o).classList.toggle("active", o === cible);
    });
  });

  /* ---------- Onglet 📊 Notes ---------- */
  function mentionBadge(mention) {
    var m = mention.toLowerCase();
    if (m.indexOf("excellent") !== -1) return '<span class="badge badge-success">' + SM.escapeHtml(mention) + "</span>";
    if (m.indexOf("très bien") !== -1) return '<span class="badge badge-info">' + SM.escapeHtml(mention) + "</span>";
    if (m.indexOf("bien") !== -1) return '<span class="badge badge-warning">' + SM.escapeHtml(mention) + "</span>";
    return '<span class="badge badge-neutral">' + SM.escapeHtml(mention) + "</span>";
  }

  function paneNotes() {
    var m = SD.moyennesEleve(eleve.id);
    if (!m.parMatiere.length) {
      return '<div class="empty-state"><div class="e-ico">📝</div><h4>Aucune note enregistrée</h4><p>Les notes seront disponibles après la première évaluation.</p></div>';
    }
    var rows = m.parMatiere.map(function (p) {
      var pct = Math.min(100, (p.moyenne / 20) * 100);
      var couleur = p.moyenne >= 14 ? "green" : p.moyenne >= 10 ? "" : "red";
      return (
        "<tr>" +
        '  <td><div class="flex-center">' + p.icone + ' <span class="fw-600">' + SM.escapeHtml(p.matiere) + "</span></div></td>" +
        '  <td class="text-center">' + p.coef + "</td>" +
        '  <td><div class="flex-center"><span class="fw-700" style="min-width:52px">' + p.moyenne.toFixed(2).replace(".", ",") + "/20</span>" +
        '    <div class="progress" style="flex:1"><div class="progress-bar ' + couleur + '" style="width:' + pct + '%"></div></div></div></td>' +
        "</tr>"
      );
    }).join("");
    var mention = SD.appreciation(m.generale);
    return (
      '<div class="notes-grid">' +
      "  <div>" +
      '    <h3 class="mb-16" style="font-size:15px">Moyennes par matière</h3>' +
      '    <div class="table-wrap"><table class="data" style="min-width:480px"><thead><tr><th>Matière</th><th class="text-center">Coef.</th><th>Moyenne</th></tr></thead><tbody>' + rows + "</tbody></table></div>" +
      "  </div>" +
      '  <div><h3 class="mb-16" style="font-size:15px">Résultat général</h3>' +
      '    <div class="card card-pad" style="text-align:center">' +
      '      <div class="text-xs text-muted fw-700" style="letter-spacing:.6px;text-transform:uppercase">Moyenne générale</div>' +
      '      <div style="font-size:44px;font-weight:800;color:var(--primary)">' + m.generale.toFixed(2).replace(".", ",") + '/20</div>' +
      '      <div class="mt-8">' + mentionBadge(mention.mention) + "</div>" +
      '      <div class="mt-8 text-sm text-muted">Rang : <b>' + (rang ? rang.rang + " / " + rang.total : "—") + "</b></div>" +
      "    </div>" +
      '    <div class="mt-16 card card-pad" style="background:#fafbfd">' +
      '      <div class="fw-700">💬 Appréciation</div>' +
      '      <p class="text-soft text-sm mt-8">' + mention.texte + "</p>" +
      "    </div>" +
      "  </div>" +
      "</div>"
    );
  }

  /* ---------- Onglet 📅 Présences ---------- */
  function panePresences() {
    var arr = SD.presences.filter(function (p) { return p.eleveId === eleve.id; });
    if (!arr.length) return '<div class="empty-state"><div class="e-ico">📅</div><h4>Aucune présence enregistrée</h4></div>';
    var nbP = arr.filter(function (p) { return p.statut === "P"; }).length;
    var nbR = arr.filter(function (p) { return p.statut === "R"; }).length;
    var nbA = arr.filter(function (p) { return p.statut === "A"; }).length;
    var taux = SD.tauxPresence(eleve.id);
    return (
      '<div class="cards-grid mb-16" style="grid-template-columns:repeat(auto-fit,minmax(130px,1fr))">' +
      '  <div class="mini-stat" style="background:var(--success-bg);border-radius:12px;padding:14px"><div class="v" style="color:var(--success-text)">' + nbP + '</div><div class="l">Présences</div></div>' +
      '  <div class="mini-stat" style="background:var(--warning-bg);border-radius:12px;padding:14px"><div class="v" style="color:var(--warning-text)">' + nbR + '</div><div class="l">Retards</div></div>' +
      '  <div class="mini-stat" style="background:var(--danger-bg);border-radius:12px;padding:14px"><div class="v" style="color:var(--danger-text)">' + nbA + '</div><div class="l">Absences</div></div>' +
      '  <div class="mini-stat" style="background:var(--info-bg);border-radius:12px;padding:14px"><div class="v" style="color:var(--info-text)">' + taux + '%</div><div class="l">Taux</div></div>' +
      "</div>" +
      '<div class="table-wrap"><table class="data" style="min-width:440px"><thead><tr><th>Date</th><th>Jour</th><th>Statut</th></tr></thead><tbody>' +
      arr.map(function (p) {
        var d = new Date(p.date + "T00:00:00");
        var jour = d.toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" });
        return "<tr><td class='fw-600'>" + SM.fmtDate(p.date) + "</td><td>" + jour + "</td><td>" + SM.badgeStatut(p.libelle) + "</td></tr>";
      }).join("") +
      "</tbody></table></div>"
    );
  }

  /* ---------- Onglet 💰 Paiements ---------- */
  function panePaiements() {
    var pai = SD.paiements.find(function (p) { return p.eleveId === eleve.id; });
    if (!pai) return '<div class="empty-state"><div class="e-ico">💰</div><h4>Pas de dossier de paiement</h4></div>';
    var paye = SD.montantPaye(pai);
    var reste = Math.max(0, pai.total - paye);
    var pct = Math.min(100, Math.round((paye / pai.total) * 100));
    var statut = SD.statutPaiement(pai);
    var barCls = statut === "Payé" ? "green" : statut === "Impayé" ? "red" : "orange";
    var rows = pai.paiements.length ? pai.paiements.map(function (v) {
      return "<tr><td>" + SM.fmtDate(v.date) + "</td><td>" + SM.escapeHtml(v.mode) + "</td><td class='fw-700'>" + SM.formatFCFA(v.montant) + "</td></tr>";
    }).join("") : '<tr><td colspan="3" style="text-align:center;color:var(--text-muted)">Aucun versement effectué pour le moment.</td></tr>';
    return (
      '<div class="notes-grid">' +
      "  <div>" +
      '    <h3 class="mb-16" style="font-size:15px">' + SM.escapeHtml(pai.motif) + "</h3>" +
      '    <div class="info-grid" style="grid-template-columns:repeat(auto-fit,minmax(140px,1fr))">' +
      '      <div class="info-cell"><div class="k">Montant total</div><div class="v">' + SM.formatFCFA(pai.total) + "</div></div>" +
      '      <div class="info-cell"><div class="k">Payé</div><div class="v text-success">' + SM.formatFCFA(paye) + "</div></div>" +
      '      <div class="info-cell"><div class="k">Reste à payer</div><div class="v" style="color:var(--danger-text)">' + SM.formatFCFA(reste) + "</div></div>" +
      "    </div>" +
      '    <div class="mt-16"><div class="flex-between mb-8"><b>' + SM.badgeStatut(statut) + "</b><b>" + pct + "%</b></div>" +
      '      <div class="progress" style="height:12px"><div class="progress-bar ' + barCls + '" style="width:' + pct + '%"></div></div></div>' +
      "  </div>" +
      "  <div>" +
      '    <h3 class="mb-16" style="font-size:15px">Historique des versements</h3>' +
      '    <div class="table-wrap"><table class="data" style="min-width:360px"><thead><tr><th>Date</th><th>Mode</th><th>Montant</th></tr></thead><tbody>' + rows + "</tbody></table></div>" +
      "  </div>" +
      "</div>"
    );
  }

  /* ---------- Onglet 📄 Bulletins ---------- */
  function paneBulletins() {
    var m = SD.moyennesEleve(eleve.id);
    return (
      '<div class="empty-state" style="padding:26px">' +
      '  <div class="e-ico">📄</div>' +
      "  <h4>Bulletins de " + SM.escapeHtml(eleve.prenom) + "</h4>" +
      '  <p class="mb-16">Générez le bulletin de l\'année ' + SD.ecole.annee + " avec le détail des notes, la moyenne générale et l'appréciation du conseil de classe.</p>" +
      '  <div class="cards-grid mb-16" style="grid-template-columns:repeat(auto-fit,minmax(220px,1fr));max-width:780px;margin:0 auto">' +
      '    <div class="card card-pad text-center"><div class="text-sm text-muted">Année scolaire</div><div class="fw-700">' + SD.ecole.annee + "</div></div>" +
      '    <div class="card card-pad text-center"><div class="text-sm text-muted">Moyenne générale</div><div class="fw-700" style="font-size:22px;color:var(--primary)">' + m.generale.toFixed(2).replace(".", ",") + "/20</div></div>" +
      '    <div class="card card-pad text-center"><div class="text-sm text-muted">Rang</div><div class="fw-700" style="font-size:22px">' + (rang ? rang.rang + "/" + rang.total : "—") + "</div></div>" +
      "  </div>" +
      '  <a class="btn btn-primary" href="report-cards.html?eleve=' + eleve.id + '">📊 Générer le bulletin scolaire</a>' +
      "</div>"
    );
  }

  /* ---------- Onglet 👨‍👩‍👦 Parent ---------- */
  function paneParent() {
    var p = eleve.parent;
    var rows = [
      ["Nom du parent", p.nom],
      ["Lien de parenté", p.lien],
      ["Téléphone", p.tel],
      ["Email", p.email],
      ["Profession", p.profession],
      ["Adresse", p.adresse + " · Ouagadougou"]
    ];
    return (
      '<div class="notes-grid">' +
      "  <div>" +
      '    <h3 class="mb-16" style="font-size:15px">👨‍👩‍👦 Responsable légal</h3>' +
      '    <div class="info-grid">' + rows.map(function (r) {
        return '<div class="info-cell"><div class="k">' + r[0] + '</div><div class="v">' + SM.escapeHtml(String(r[1])) + "</div></div>";
      }).join("") + "</div>" +
      "  </div>" +
      '  <div><h3 class="mb-16" style="font-size:15px">Contact rapide</h3>' +
      '    <div class="card card-pad">' +
      '      <div class="settings-row"><div><div class="s-k">📞 Téléphone</div><div class="s-d">Contacter le parent</div></div><a class="btn btn-outline btn-sm" href="tel:' + SM.escapeHtml(p.tel.replace(/\s/g, "")) + '">Appeler</a></div>' +
      '      <div class="settings-row"><div><div class="s-k">✉️ Email</div><div class="s-d">Envoyer un message</div></div><a class="btn btn-outline btn-sm" href="mailto:' + SM.escapeHtml(p.email) + '">Écrire</a></div>' +
      '      <div class="settings-row"><div><div class="s-k">📍 Adresse</div><div class="s-d">' + SM.escapeHtml(p.adresse) + " · Ouagadougou</div></div></div>" +
      "    </div>" +
      '    <div class="alert alert-info mt-16">💡 En cas d\'urgence, contactez le secrétariat au <b>' + SD.ecole.telephone + "</b>.</div>" +
      "  </div>" +
      "</div>"
    );
  }

  /* ---------- Remplissage des onglets ---------- */
  document.getElementById("pane-notes").innerHTML = paneNotes();
  document.getElementById("pane-presences").innerHTML = panePresences();
  document.getElementById("pane-paiements").innerHTML = panePaiements();
  document.getElementById("pane-bulletins").innerHTML = paneBulletins();
  document.getElementById("pane-parent").innerHTML = paneParent();
})();
