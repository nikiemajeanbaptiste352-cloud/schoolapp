/* ============================================================
   SchoolManager — Tableau de bord
   ============================================================ */

(function () {
  "use strict";

  var SM = window.SM;
  var SD = window.SD;

  /* ---------- Bienvenue ---------- */
  // Identité : celle décidée par le serveur (`/etat` → `moi`), avec
  // `sessionStorage` en simple repli d'affichage.
  var sess = SM.getSession();
  var moi = window.SM_MOI || {};
  var role = SM.roleCourant() || (sess ? sess.role : "Administrateur");
  var nom = moi.nom || (sess && sess.nom !== "Administrateur" ? sess.nom : "");
  var estFamille = role === "Élève" || role === "Parent";
  var estProf = role === "Professeur";
  var estSurveillant = role === "Surveillant";
  document.getElementById("heroTitle").textContent = "Bonjour " + (nom || role) + " 👋";

  // Sous-titre du bandeau : il annonce ce que le profil a réellement sous les
  // yeux, pas l'activité de l'établissement à quelqu'un qui n'en voit qu'une
  // partie.
  var SOUS_TITRES_HERO = {
    Administrateur: "Voici un aperçu de l'activité de votre établissement aujourd'hui.",
    Professeur: "Voici l'activité de vos classes et vos dernières séances.",
    Surveillant: "Voici l'état des effectifs et le suivi des présences.",
    "Élève": "Voici votre scolarité en un coup d'œil : notes, présences et paiements.",
    Parent: "Voici la scolarité de votre enfant : notes, présences et paiements."
  };
  document.getElementById("heroSub").textContent = SOUS_TITRES_HERO[role] || SOUS_TITRES_HERO.Administrateur;

  var heroYearEl = document.getElementById("heroYear");
  if (SD.ecole.annee) { heroYearEl.textContent = "📅 Année scolaire " + SD.ecole.annee; }
  else { heroYearEl.style.display = "none"; }

  /* ---------- Statistiques ---------- */
  var actifs = SD.eleves.filter(function (e) { return e.statut === "Actif"; }).length;
  var presences = SD.eleves.length
    ? Math.round(SD.eleves.reduce(function (s, e) { return s + SD.tauxPresence(e.id); }, 0) / SD.eleves.length)
    : 0;
  // Le périmètre peut ne contenir qu'un élève (parent, élève) : on vise le
  // premier élève accessible plutôt qu'un identifiant codé en dur.
  var premier = SD.eleves.length ? SD.eleves[0] : null;
  var lienFiche = premier ? "student-profile.html?id=" + premier.id : "students.html";

  // Chaque profil a ses indicateurs : une direction suit des effectifs, un
  // parent suit les résultats et le solde de son enfant. Afficher « Élèves
  // inscrits : 15 » à un parent serait un chiffre de l'établissement dont il
  // n'a pas la vue.
  var stats;
  if (estFamille) {
    var moy = premier ? SD.moyennesEleve(premier.id).generale : 0;
    var rang = premier ? SD.rangEleve(premier.id) : null;
    var pai = premier ? SD.paiements.find(function (x) { return x.eleveId === premier.id; }) : null;
    var paye = pai ? SD.montantPaye(pai) : 0;
    var reste = pai ? Math.max(0, pai.total - paye) : 0;
    var taux = premier ? SD.tauxPresence(premier.id) : 0;
    stats = [
      { ico: "📝", cls: "blue", value: moy.toFixed(2) + "/20", label: "Moyenne générale",
        delta: SD.appreciation(moy).mention, lien: "grades.html" },
      { ico: "🏅", cls: "orange", value: rang ? rang.rang + (rang.rang === 1 ? "er" : "e") : "—", label: "Rang en classe",
        delta: rang ? "sur " + rang.total + " élèves" : "non classé", lien: "report-cards.html" },
      { ico: "✅", cls: "green", value: taux + "%", label: "Taux de présence",
        delta: "sur l'année en cours", lien: lienFiche },
      { ico: "💰", cls: "red", value: reste > 0 ? SM.formatFCFA(reste) : "À jour", label: "Solde de scolarité",
        delta: pai ? SD.statutPaiement(pai) : "aucun frais enregistré", lien: "payments.html" }
    ];
  } else if (estProf) {
    stats = [
      { ico: "🏫", cls: "orange", value: SD.classes.length, label: "Mes classes",
        delta: SD.classes.length ? "où j'enseigne" : "—", lien: "classes.html" },
      { ico: "📚", cls: "blue", value: SD.matieres.length, label: "Mes matières",
        delta: SD.matieres.length ? "au programme" : "—", lien: "subjects.html" },
      { ico: "👨‍🎓", cls: "green", value: SD.eleves.length, label: "Mes élèves",
        delta: actifs + " actifs", lien: "students.html" },
      { ico: "✅", cls: "red", value: presences + "%", label: "Présence moyenne",
        delta: "dans mes classes", lien: "mes-seances.html" }
    ];
  } else if (estSurveillant) {
    stats = [
      { ico: "👨‍🎓", cls: "blue", value: SD.eleves.length, label: "Élèves suivis",
        delta: actifs + " actifs", lien: "students.html" },
      { ico: "🏫", cls: "orange", value: SD.classes.length, label: "Classes",
        delta: SD.classes.length ? "à surveiller" : "—", lien: "classes.html" },
      { ico: "✅", cls: "red", value: presences + "%", label: "Présence moyenne",
        delta: "toutes classes", lien: "students.html" },
      { ico: "👨‍🏫", cls: "green", value: SD.enseignants.length, label: "Enseignants",
        delta: "équipe en place", lien: "teachers.html" }
    ];
  } else {
    stats = [
      { ico: "👨‍🎓", cls: "blue", value: SD.eleves.length, label: "Élèves inscrits",
        delta: actifs + " actifs", lien: "students.html" },
      { ico: "👨‍🏫", cls: "green", value: SD.enseignants.length, label: "Enseignants",
        delta: SD.enseignants.length ? "équipe en place" : "—", lien: "teachers.html" },
      { ico: "🏫", cls: "orange", value: SD.classes.length, label: "Classes",
        delta: SD.classes.length ? "Collège & Lycée" : "—", lien: "classes.html" },
      { ico: "✅", cls: "red", value: presences + "%", label: "Présence moyenne",
        delta: SD.eleves.length ? "historique des présences" : "—", lien: lienFiche }
    ];
  }

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
  // `SD.paiements` est déjà réduit au périmètre par le serveur : pour un
  // professeur ou un surveillant la liste est vide. On filtre les élèves
  // sans paiement visible au lieu de supposer qu'il y en a un — sinon un
  // simple compte sans versement faisait échouer tout le tableau de bord.
  var pays = SD.eleves.map(function (e) {
    var p = SD.paiements.find(function (x) { return x.eleveId === e.id; });
    return { eleve: e, pai: p };
  }).filter(function (o) {
    return o.pai && o.pai.paiements && o.pai.paiements.length;
  }).sort(function (a, b) {
    var da = a.pai.paiements[a.pai.paiements.length - 1].date;
    var db = b.pai.paiements[b.pai.paiements.length - 1].date;
    return db.localeCompare(da);
  }).slice(0, 5);

  document.getElementById("recentPayments").innerHTML = pays.length ? pays.map(function (o) {
    var nomC = o.eleve.nom + " " + o.eleve.prenom;
    var reste = Math.max(0, o.pai.total - SD.montantPaye(o.pai));
    var badge = SM.badgeStatut(SD.statutPaiement(o.pai));
    var mnt = SD.montantPaye(o.pai) ? SM.formatFCFA(SD.montantPaye(o.pai)) : "Aucun versement";
    var classe = SD.getClasse(o.eleve.classe);
    return (
      '<div class="list-item">' +
      SM.avatarHTML(nomC, "sm") +
      '  <div class="pay-mini">' +
      '    <div><div class="fw-600" style="font-size:14px">' + SM.escapeHtml(nomC) + "</div>" +
      '      <div class="text-xs text-muted">' + SM.escapeHtml(classe ? classe.nom : "—") + " · Reste : " + (reste > 0 ? SM.formatFCFA(reste) : "—") + "</div></div>" +
      "    <div style='text-align:right'>" + badge + '<div class="v mt-8" style="margin-top:4px;font-weight:600;font-size:13px">' + mnt + "</div></div>" +
      "  </div>" +
      "</div>"
    );
  }).join("") : '<div class="text-sm text-muted">Aucun paiement à afficher avec votre profil.</div>';

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

  /* ---------- Habillage selon le rôle ----------
     Outre les chiffres, on adapte les intitulés des cartes et on retire les
     raccourcis qui mèneraient à une page interdite (le serveur refuse, mais
     mieux vaut ne pas proposer l'aller-retour). */
  function fixer(id, texte) {
    var n = document.getElementById(id);
    if (n) n.textContent = texte;
  }

  var portee = SM.porteeEleves();
  if (estFamille) {
    fixer("titreRepartition", portee === "aucun"
      ? "🏫 Classes de l'établissement"
      : "🏫 Effectif de la classe");
    fixer("lienRepartition", "Voir →");
    fixer("titrePaiements", role === "Parent" ? "💳 Ses derniers paiements" : "💳 Mes derniers paiements");
    fixer("lienPaiements", "Voir →");
  } else if (estSurveillant) {
    fixer("titreRepartition", "🏫 Effectifs par classe");
  }

  // Le détail des paiements ne concerne pas l'encadrement pédagogique : la
  // carte disparaît au lieu d'afficher un message vide permanent.
  if (role === "Professeur" || estSurveillant) {
    var cartePaiements = document.getElementById("cartePaiements");
    if (cartePaiements) cartePaiements.style.display = "none";
  }

  // Raccourcis : uniquement ceux dont la page est ouverte à ce profil.
  var grille = document.getElementById("quickGrid");
  if (grille) {
    var liens = grille.querySelectorAll("[data-page-cap]");
    for (var k = 0; k < liens.length; k++) {
      var cle = liens[k].getAttribute("data-page-cap");
      if (!SM.pageAutorisee(cle, role)) liens[k].style.display = "none";
    }
  }
})();
