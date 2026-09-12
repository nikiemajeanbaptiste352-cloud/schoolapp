/* ============================================================
   SchoolManager — 📋 Vie scolaire (appel & présences)
   ------------------------------------------------------------
   L'écran qui manquait : `presences.ecrire` est accordé à
   l'Administrateur, au Professeur et au Surveillant, mais aucune
   page ne permettait de saisir un appel — les présences
   n'étaient visibles qu'en lecture sur la fiche élève.

   Déroulé : on choisit une classe et un jour, l'élève est marqué
   Présent (P) / Retard (R) / Absent (A), puis on enregistre.
   Le serveur reste seul juge : la route
   `POST /api/v1/presences` (Administrateur, Professeur,
   Surveillant) upsert la présence par (élève, date).
   ============================================================ */

(function () {
  "use strict";

  var SM = window.SM;
  var API = window.API;
  var SD = window.SD;

  // La décision d'ouvrir la page vient du serveur (capacités de
  // GET /api/v1/etat), pas du navigateur.
  if (!SM.pageAutorisee("vie-scolaire", SM.roleCourant())) {
    window.location.replace("dashboard.html");
    return;
  }

  var role = SM.roleCourant();
  var peutPointer = SM.peut("presences.ecrire");
  // Un professeur reconnaît ses classes à sa fiche enseignant (même
  // rapprochement que sur classes.html / subjects.html).
  var maFiche = role === "Professeur" ? SM.monEnseignant(SD) : null;
  var mesClasses = maFiche && maFiche.classes ? maFiche.classes : [];

  var LIB = { P: "Présent", R: "Retard", A: "Absent" };
  var ORDRE = ["P", "R", "A"]; // ordre des boutons de pointage

  var classeSel = null;   // code de la classe affichée
  var jourSel = null;     // AAAA-MM-JJ
  var statuts = {};       // {eleveId: "P"|"R"|"A"} — pointage à l'écran
  var enregistres = {};   // {eleveId: "P"|"R"|"A"|null} — dernier état serveur
  var enCours = false;    // anti double-clic pendant l'enregistrement

  function el(id) { return document.getElementById(id); }
  function esc(s) { return SM.escapeHtml(s); }

  /* ---------- Dates ---------- */
  var JOURS = ["dimanche", "lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi"];
  var MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
    "août", "septembre", "octobre", "novembre", "décembre"];

  function iso(d) {
    return d.getFullYear() + "-" + ("0" + (d.getMonth() + 1)).slice(-2) + "-" + ("0" + d.getDate()).slice(-2);
  }
  function aujourdhui() { return iso(new Date()); }

  /* « lundi 10 septembre 2026 » */
  function jourLong(v) {
    if (!v || !/^\d{4}-\d{2}-\d{2}$/.test(v)) return v || "—";
    var d = new Date(v + "T00:00:00");
    if (isNaN(d)) return v;
    return JOURS[d.getDay()] + " " + d.getDate() + " " + MOIS[d.getMonth()] + " " + d.getFullYear();
  }

  function erreur(e) {
    var msg = (e && e.detail) ? e.detail : (e && e.message) ? e.message : "Erreur inconnue.";
    SM.toast(esc(msg), "error");
  }

  /* ---------- Roster & état du jour ---------- */
  function roster() { return SD.elevesDeClasse(classeSel); }

  // Statut enregistré pour (élève, jour) d'après l'instantané du serveur.
  function statutServeur(eleveId) {
    for (var i = 0; i < SD.presences.length; i++) {
      var p = SD.presences[i];
      if (p.eleveId === eleveId && p.date === jourSel) return p.statut;
    }
    return null;
  }

  function charger() {
    statuts = {};
    enregistres = {};
    roster().forEach(function (e) {
      var s = statutServeur(e.id);
      enregistres[e.id] = s;
      statuts[e.id] = s || "P"; // par défaut : présent, l'appel se fait par exception
    });
  }

  function compte(cle) {
    var n = 0;
    roster().forEach(function (e) { if (statuts[e.id] === cle) n++; });
    return n;
  }

  function nonEnregistres() {
    var n = 0;
    roster().forEach(function (e) { if (!enregistres[e.id]) n++; });
    return n;
  }

  /* Pointages locaux qui s'écartent de ce que le serveur a déjà enregistré.
     Un élève jamais enregistré n'est pas une « modification » : il est compté par nonEnregistres(). */
  function modifies() {
    var liste = [];
    roster().forEach(function (e) {
      if (enregistres[e.id] && statuts[e.id] !== enregistres[e.id]) liste.push(e.id);
    });
    return liste;
  }

  /* ---------- Rendu : compteurs, note, tableau ---------- */
  function rendreCompteurs() {
    var n = roster().length;
    var p = compte("P"), r = compte("R"), a = compte("A");
    var taux = n ? Math.round(((p + r) / n) * 100) : 0;
    el("miniCounts").innerHTML =
      '<div class="mini-stat"><div class="v">' + n + '</div><div class="l">Effectif</div></div>' +
      '<div class="mini-stat"><div class="v" style="color:var(--success)">' + p + '</div><div class="l">Présents</div></div>' +
      '<div class="mini-stat"><div class="v" style="color:var(--warning)">' + r + '</div><div class="l">Retards</div></div>' +
      '<div class="mini-stat"><div class="v" style="color:var(--danger)">' + a + '</div><div class="l">Absents</div></div>' +
      '<div class="mini-stat"><div class="v">' + taux + '%</div><div class="l">Présence du jour</div></div>';
  }

  function rendreNote() {
    var note = el("noteJour");
    var n = roster().length;
    if (!n) { note.style.display = "none"; note.innerHTML = ""; return; }

    var restants = nonEnregistres();
    var changes = modifies();
    var titre = "<strong>" + esc(jourLong(jourSel)) + "</strong> — classe " + esc(libelleClasse(classeSel)) + ".";
    var detail = " " + compte("P") + " présent(s), " + compte("R") + " retard(s), " + compte("A") + " absent(s).";
    note.style.display = "";

    if (changes.length) {
      /* Un pointage fait à l'écran n'est pas encore parti au serveur : cet état prime sur le reste
         (sinon l'alerte resterait verte alors que l'appel affiché n'est pas celui qui est enregistré). */
      note.innerHTML = '<div class="alert alert-ico alert-warning">⚠️ <div>' + changes.length +
        " modification(s) non enregistrée(s) pour " + titre + detail +
        (restants ? " " + restants + " élève(s) sur " + n + " sans statut enregistré." : "") +
        "</div></div>";
    } else if (restants === 0) {
      note.innerHTML = '<div class="alert alert-ico alert-success">✅ <div>Appel enregistré. ' + titre + detail +
        "</div></div>";
    } else if (restants < n) {
      note.innerHTML = '<div class="alert alert-ico alert-warning">⚠️ <div>Aucun appel complet pour ' + titre +
        " " + restants + " élève(s) sur " + n + " sans statut enregistré.</div></div>";
    } else {
      note.innerHTML = '<div class="alert alert-ico alert-info">📋 <div>Aucun appel enregistré pour ' + titre +
        " Le pointage proposé est « présent » pour tout le monde : cochez les exceptions puis enregistrez." +
        "</div></div>";
    }
  }

  function rendreTable() {
    var tbody = el("tableBody");
    var liste = roster();

    if (!liste.length) {
      tbody.innerHTML =
        '<tr><td colspan="4"><div class="empty-state"><div class="e-ico">👨‍🎓</div><h4>Aucun élève dans cette classe</h4>' +
        "<p>Choisissez une autre classe pour faire l'appel.</p></div></td></tr>";
      el("countLabel").textContent = "0 élève";
      return;
    }

    tbody.innerHTML = liste.map(function (e) {
      var nomC = e.nom + " " + e.prenom;
      var srv = enregistres[e.id];
      var boutons = ORDRE.map(function (s) {
        var cls = statuts[e.id] === s ? " class=\"on-" + s + "\"" : "";
        return "<button type=\"button\"" + cls + ' data-eleve="' + esc(e.id) + '" data-statut="' + s +
          '"' + (peutPointer ? "" : " disabled") + ' title="' + LIB[s] + '">' + s + "</button>";
      }).join("");
      return (
        "<tr>" +
        "  <td><div class='cell-user'>" + SM.avatarHTML(nomC, "sm") +
        '    <div><div class="names">' + esc(e.nom) + " " + esc(e.prenom) +
        '      </div><div class="sub">Matricule : ' + esc(e.id) + "</div></div></div></td>" +
        '  <td><span class="chip">' + esc(libelleClasse(e.classe)) + "</span></td>" +
        "  <td>" + (srv ? SM.badgeStatut(LIB[srv]) : '<span class="text-muted text-sm">—</span>') + "</td>" +
        '  <td><div class="ptg" style="justify-content:center">' + boutons + "</div></td>" +
        "</tr>"
      );
    }).join("");

    el("countLabel").textContent = liste.length + " élève" + (liste.length > 1 ? "s" : "") +
      " — appel du " + jourLong(jourSel);
  }

  function libelleClasse(id) {
    var c = SD.getClasse(id);
    return c ? c.nom : (id || "—");
  }

  /* ---------- Élèves à suivre (assiduité la plus faible) ---------- */
  function rendreSuivi() {
    var ligne = SD.eleves.map(function (e) {
      var arr = SD.presences.filter(function (p) { return p.eleveId === e.id; });
      var abs = arr.filter(function (p) { return p.statut === "A"; }).length;
      return { e: e, taux: SD.tauxPresence(e.id), abs: abs, releves: arr.length };
    }).filter(function (x) { return x.releves > 0; });

    ligne.sort(function (a, b) { return a.taux - b.taux || b.abs - a.abs; });
    var bas = ligne.filter(function (x) { return x.taux < 90; }).slice(0, 6);
    var zone = el("listeSuivi");
    var carte = el("carteSuivi");

    if (!bas.length) {
      carte.style.display = "none";
      return;
    }
    carte.style.display = "";
    zone.innerHTML =
      '<div class="bars">' +
      bas.map(function (x) {
        var c = SD.getClasse(x.e.classe);
        return (
          '<div class="bar-row">' +
          '  <div class="bar-top"><b>' + esc(x.e.nom) + " " + esc(x.e.prenom) + "</b><span>" +
          x.taux + "% — " + x.abs + " absence" + (x.abs > 1 ? "s" : "") +
          (c ? " • " + esc(c.nom) : "") + "</span></div>" +
          '  <div class="bar-track"><div class="bar-fill" style="width:' + x.taux + '%"></div></div>' +
          "</div>"
        );
      }).join("") +
      "</div>" +
      '<div class="mt-8 text-sm text-muted">Seuil de vigilance : moins de <b>90 %</b> de présence sur les ' +
      ligne.reduce(function (s, x) { return s + x.releves; }, 0) + " relevés enregistrés.</div>";
  }

  /* ---------- Enregistrement ---------- */
  function enregistrer() {
    if (enCours) return;
    if (!peutPointer) {
      SM.toast("Votre profil n'est pas habilité à enregistrer l'appel.", "error");
      return;
    }
    var liste = roster();
    if (!liste.length) {
      SM.toast("Aucun élève à pointer dans cette classe.", "warning");
      return;
    }
    var corps = { classe: classeSel, date: jourSel, statuts: {} };
    liste.forEach(function (e) { corps.statuts[e.id] = statuts[e.id] || "P"; });

    enCours = true;
    var btn = el("btnSave");
    var libelle = btn ? btn.innerHTML : "";
    if (btn) { btn.disabled = true; btn.innerHTML = "⏳ Enregistrement…"; }

    API.pointerPresence(corps).then(function (rep) {
      // Report local : l'appel devient l'état de référence sans recharger
      // la page (les listes du tableau de bord se rafraîchissent au retour).
      liste.forEach(function (e) {
        var s = corps.statuts[e.id];
        enregistres[e.id] = s;
        var trouve = false;
        for (var i = 0; i < SD.presences.length; i++) {
          var p = SD.presences[i];
          if (p.eleveId === e.id && p.date === jourSel) { p.statut = s; p.libelle = LIB[s]; trouve = true; break; }
        }
        if (!trouve) SD.presences.push({ eleveId: e.id, date: jourSel, statut: s, libelle: LIB[s] });
      });
      rendreCompteurs();
      rendreNote();
      rendreTable();
      rendreSuivi();
      SM.toast(esc((rep && rep.message) || "Appel enregistré."), "success");
    }).catch(function (e) {
      erreur(e);
    }).then(function () {
      enCours = false;
      if (btn) { btn.disabled = false; btn.innerHTML = libelle; }
    });
  }

  /* ---------- Changement de classe / de jour ---------- */
  function chargerClasses() {
    var options = SD.classes.map(function (c) {
      var n = SD.elevesDeClasse(c.id).length;
      var star = mesClasses.indexOf(c.id) !== -1 ? "⭐ " : "";
      return '<option value="' + esc(c.id) + '">' + star + esc(c.nom) + " — " + n + " élève" + (n > 1 ? "s" : "") + "</option>";
    }).join("");
    el("selClasse").innerHTML = options;

    // Par défaut : la première classe où l'on enseigne (professeur), sinon
    // la classe la plus nombreuse — un surveillant ou un administrateur
    // ouvre l'appel sur le groupe le plus large, pas sur la première classe
    // de la liste (souvent un effectif de un).
    var cible = null;
    for (var i = 0; i < mesClasses.length; i++) {
      if (SD.elevesDeClasse(mesClasses[i]).length) { cible = mesClasses[i]; break; }
    }
    if (!cible) {
      var plus = 0;
      for (var j = 0; j < SD.classes.length; j++) {
        var effectif = SD.elevesDeClasse(SD.classes[j].id).length;
        if (effectif > plus) { plus = effectif; cible = SD.classes[j].id; }
      }
    }
    classeSel = cible || (SD.classes[0] ? SD.classes[0].id : null);
    if (classeSel) el("selClasse").value = classeSel;
  }

  function changerClasse() {
    charger();
    rendreCompteurs();
    rendreNote();
    rendreTable();
  }

  function changerJour(v) {
    if (!v) return;
    if (v > aujourdhui()) {
      SM.toast("L'appel ne peut pas être saisi pour une date future.", "warning");
      el("jourInput").value = jourSel;
      return;
    }
    jourSel = v;
    charger();
    rendreCompteurs();
    rendreNote();
    rendreTable();
  }

  /* ---------- Feuille d'appel imprimable ---------- */
  function imprimer() {
    var liste = roster();
    if (!liste.length) { SM.toast("Aucun élève à imprimer pour cette classe.", "warning"); return; }
    var ecole = SD.ecole || {};
    var lignes = liste.map(function (e, i) {
      var st = statuts[e.id];
      function box(s) { return '<td style="text-align:center">' + (st === s ? "✔" : "☐") + "</td>"; }
      return "<tr>" +
        '<td style="text-align:center">' + (i + 1) + "</td>" +
        "<td>" + esc(e.nom) + " " + esc(e.prenom) + "</td>" +
        '<td style="text-align:center">' + esc(e.id) + "</td>" +
        box("P") + box("R") + box("A") +
        '<td style="width:170px"></td>' +
        "</tr>";
    }).join("");

    var n = liste.length;
    var taux = n ? Math.round(((compte("P") + compte("R")) / n) * 100) : 0;
    el("feuillePrint").innerHTML =
      '<div class="print-area">' +
      '  <h1 style="font-size:20px;margin:0 0 4px">Feuille d\'appel</h1>' +
      '  <div style="font-size:14px;font-weight:700">' + esc(ecole.nom || "Établissement") + "</div>" +
      '  <div style="font-size:12.5px;color:#475569;margin-bottom:12px">' +
      "Classe : <b>" + esc(libelleClasse(classeSel)) + "</b> — Jour : <b>" + esc(jourLong(jourSel)) + "</b>" +
      (ecole.annee ? " — Année scolaire " + esc(ecole.annee) : "") +
      (maFiche ? " — Enseignant : " + esc(maFiche.nom + " " + maFiche.prenom) : "") +
      "  </div>" +
      '  <table class="data">' +
      "    <thead><tr><th style='width:34px'>N°</th><th>Nom et prénom</th><th style='width:100px;text-align:center'>Matricule</th>" +
      "      <th style='width:70px;text-align:center'>Présent</th><th style='width:70px;text-align:center'>Retard</th>" +
      "      <th style='width:70px;text-align:center'>Absent</th><th style='width:170px'>Observation</th></tr></thead>" +
      "    <tbody>" + lignes + "</tbody>" +
      "  </table>" +
      '  <div style="margin-top:10px;font-size:12.5px">' +
      "Effectif : <b>" + n + "</b> — Présents : <b>" + compte("P") + "</b> — Retards : <b>" + compte("R") +
      "</b> — Absents : <b>" + compte("A") + "</b> — Taux de présence : <b>" + taux + "%</b>" +
      "  </div>" +
      '  <div style="margin-top:26px;display:flex;justify-content:space-between;font-size:12.5px">' +
      "    <div>Signature du surveillant : ______________________</div>" +
      "    <div>Visa de la direction : ______________________</div>" +
      "  </div>" +
      "</div>";

    window.print();
  }

  /* ---------- Mise en place ---------- */
  function init() {
    var champJour = el("jourInput");
    champJour.max = aujourdhui();
    champJour.value = aujourdhui();
    jourSel = aujourdhui();

    chargerClasses();
    charger();
    rendreCompteurs();
    rendreNote();
    rendreTable();
    rendreSuivi();

    el("selClasse").addEventListener("change", function () {
      classeSel = this.value;
      changerClasse();
    });
    champJour.addEventListener("change", function () { changerJour(this.value); });
    el("btnAujourdhui").addEventListener("click", function () {
      champJour.value = aujourdhui();
      changerJour(aujourdhui());
    });

    el("btnTousPresents").addEventListener("click", function () {
      if (!peutPointer) return;
      roster().forEach(function (e) { statuts[e.id] = "P"; });
      rendreCompteurs();
      rendreNote();
      rendreTable();
      SM.toast("Toute la classe est marquée présente. Enregistrez pour valider.", "info");
    });

    el("btnSave").addEventListener("click", enregistrer);
    el("btnPrint").addEventListener("click", imprimer);

    // Pointage : un clic par élève, sans quitter la ligne.
    el("tableBody").addEventListener("click", function (ev) {
      var b = ev.target;
      if (!b || !b.getAttribute || !b.getAttribute("data-eleve")) return;
      if (!peutPointer) return;
      var id = b.getAttribute("data-eleve");
      var s = b.getAttribute("data-statut");
      if (!LIB[s]) return;
      statuts[id] = s;
      rendreCompteurs();
      rendreNote();
      rendreTable();
    });
  }

  init();
})();
