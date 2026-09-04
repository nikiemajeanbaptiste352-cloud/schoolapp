/* ============================================================
   SchoolManager — Tableau de bord
   ============================================================ */

(function () {
  "use strict";

  var SM = window.SM;
  var SD = window.SD;

  /* ---------- Bienvenue ---------- */
  var sess = SM.getSession();
  var role = sess ? sess.role : "Administrateur";
  var nom = sess && sess.nom !== "Administrateur" ? sess.nom : "";
  document.getElementById("heroTitle").textContent = "Bonjour " + (nom || role) + " 👋";
  var heroYearEl = document.getElementById("heroYear");
  if (SD.ecole.annee) { heroYearEl.textContent = "📅 Année scolaire " + SD.ecole.annee; }
  else { heroYearEl.style.display = "none"; }

  /* ---------- Statistiques ---------- */
  var actifs = SD.eleves.filter(function (e) { return e.statut === "Actif"; }).length;
  var presences = SD.eleves.length
    ? Math.round(SD.eleves.reduce(function (s, e) { return s + SD.tauxPresence(e.id); }, 0) / SD.eleves.length)
    : 0;

  var stats = [
    { ico: "👨‍🎓", cls: "blue", value: SD.eleves.length, label: "Élèves inscrits", delta: actifs + " actifs", lien: "students.html" },
    { ico: "👨‍🏫", cls: "green", value: SD.enseignants.length, label: "Enseignants", delta: SD.enseignants.length ? "équipe en place" : "—", lien: "teachers.html" },
    { ico: "🏫", cls: "orange", value: SD.classes.length, label: "Classes", delta: SD.classes.length ? "Collège & Lycée" : "—", lien: "classes.html" },
    { ico: "✅", cls: "red", value: presences + "%", label: "Présence moyenne", delta: SD.eleves.length ? "historique des présences" : "—", lien: "student-profile.html?id=EL001" }
  ];

  var statsHTML = stats.map(function (s) {
    return (
      '<div class="stat-card" onclick="location.href=\'' + s.lien + '\'">' +
      '  <div class="stat-ico ' + s.cls + '">' + s.ico + "</div>" +
      '  <div><div class="stat-value">' + s.value + '</div><div class="stat-label">' + s.label +
      '  </div><div class="stat-delta up">' + s.delta + "</div></div>" +
      "</div>"
    );
  }).join("");
  document.getElementById("statsCards").innerHTML = statsHTML;

  /* ---------- Répartition par classe ---------- */
  var counts = SD.classes.map(function (c) {
    return { nom: c.nom, n: SD.eleves.filter(function (e) { return e.classe === c.id; }).length };
  });
  var max = Math.max.apply(null, counts.map(function (c) { return c.n; }).concat([1]));
  var total = counts.reduce(function (s, c) { return s + c.n; }, 0);
  document.getElementById("classBars").innerHTML =
    '<div class="bars">' +
    counts.map(function (c) {
      var pct = Math.round((c.n / max) * 100);
      return (
        '<div class="bar-row">' +
        '  <div class="bar-top"><b>' + c.nom + "</b><span>" + c.n + " élève" + (c.n > 1 ? "s" : "") + "</span></div>" +
        '  <div class="bar-track"><div class="bar-fill" style="width:' + pct + '%"></div></div>' +
        "</div>"
      );
    }).join("") +
    "</div>" +
    '<div class="mt-8 text-sm text-muted">Total : <b>' + total + "</b> élèves répartis dans <b>" + SD.classes.length + "</b> classes.</div>";

  /* ---------- Derniers paiements ---------- */
  var pays = SD.eleves.map(function (e) {
    var p = SD.paiements.find(function (x) { return x.eleveId === e.id; });
    return { eleve: e, pai: p };
  }).sort(function (a, b) {
    var da = a.pai && a.pai.paiements.length ? a.pai.paiements[a.pai.paiements.length - 1].date : "";
    var db = b.pai && b.pai.paiements.length ? b.pai.paiements[b.pai.paiements.length - 1].date : "";
    return db.localeCompare(da);
  }).slice(0, 5);

  document.getElementById("recentPayments").innerHTML = pays.map(function (o) {
    var nomC = o.eleve.nom + " " + o.eleve.prenom;
    var reste = Math.max(0, o.pai.total - SD.montantPaye(o.pai));
    var badge = SM.badgeStatut(SD.statutPaiement(o.pai));
    var mnt = SD.montantPaye(o.pai) ? SM.formatFCFA(SD.montantPaye(o.pai)) : "Aucun versement";
    return (
      '<div class="list-item">' +
      SM.avatarHTML(nomC, "sm") +
      '  <div class="pay-mini">' +
      '    <div><div class="fw-600" style="font-size:14px">' + SM.escapeHtml(nomC) + "</div>" +
      '      <div class="text-xs text-muted">' + SM.escapeHtml(SD.getClasse(o.eleve.classe).nom) + " · Reste : " + (reste > 0 ? SM.formatFCFA(reste) : "—") + "</div></div>" +
      "    <div style='text-align:right'>" + badge + '<div class="v mt-8" style="margin-top:4px;font-weight:600;font-size:13px">' + mnt + "</div></div>" +
      "  </div>" +
      "</div>"
    );
  }).join("");

  /* ---------- Annonces récentes ---------- */
  var ann = SD.annonces.slice().sort(function (a, b) { return b.date.localeCompare(a.date); }).slice(0, 4);
  document.getElementById("recentAnnounces").innerHTML = ann.map(function (a) {
    return (
      '<a href="announcements.html" class="list-item" style="text-decoration:none;color:inherit">' +
      '  <span style="font-size:20px">' + (a.important ? "🔴" : "📢") + "</span>" +
      '  <div class="announce-mini">' +
      '    <div class="am-t">' + SM.escapeHtml(a.titre) + "</div>" +
      '    <div class="am-d"><span>' + SM.fmtDate(a.date) + '</span><span class="chip chip-plain">' + SM.escapeHtml(a.categorie) + "</span></div>" +
      "  </div>" +
      "</a>"
    );
  }).join("");
})();
