/* ============================================================
   SchoolManager — Données
   ------------------------------------------------------------
   La fabrique construireSD(d) attache les fonctions de calcul
   (moyennes, classement, emploi du temps…) à un jeu de données
   { ecole, classes, matieres, enseignants, eleves, notes,
     presences, paiements, annonces }.

   Mode unique : js/live.js récupère GET /api/v1/etat puis
   reconstruit window.SD via construireSD(donneesServeur).
   L'application ne contient AUCUNE donnée fictive : les pages
   n'affichent que ce qui est réellement présent dans la base.
   ============================================================ */

(function () {
  "use strict";

  /* ---------- Générateur déterministe (résultats stables) ---------- */
  function rand(n) {
    // Petit générateur pseudo-aléatoire déterministe
    var x = Math.sin(n) * 10000;
    return x - Math.floor(x);
  }

  /* ---------- Constantes partagées ---------- */
  var EVALS = ["Devoir 1", "Devoir 2", "Composition"];
  var JOURS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi"];
  var CRENEAUX = [
    { label: "07h30 – 09h00", pause: false },
    { label: "09h00 – 10h30", pause: false },
    { label: "10h45 – 12h15", pause: true },   // mercredi après-midi libre
    { label: "15h00 – 16h30", pause: false }
  ];
  var LIB_PRESENCE = { P: "Présent", R: "Retard", A: "Absent" };

  /* =========================================================
     FABRIQUE SD — construireSD(donnees)
     ========================================================= */
  function construireSD(d) {
    var ecole = d.ecole;
    var classes = d.classes;
    var matieres = d.matieres;
    var enseignants = d.enseignants;
    var eleves = d.eleves;
    var notes = d.notes;
    var presences = d.presences;
    var paiements = d.paiements;
    var annonces = d.annonces;

    function matieresDeClasse(classeId) {
      var cls = getClasse(classeId);
      var base = ["S1", "S2", "S3", "S4", "S5", "S6", "S7"];
      var ids = cls && cls.cycle === "Lycée"
        ? ["S1", "S2", "S3", "S4", "S5", "S6", "S8", "S7"]
        : base;
      return matieres.filter(function (m) { return ids.indexOf(m.id) !== -1; });
    }

    function getClasse(id) { return classes.find(function (c) { return c.id === id; }); }
    function getMatiere(id) { return matieres.find(function (m) { return m.id === id; }); }
    function getEnseignant(id) { return enseignants.find(function (e) { return e.id === id; }); }
    function getEleve(id) { return eleves.find(function (e) { return e.id === id; }); }

    function elevesDeClasse(classeId) {
      return eleves
        .filter(function (e) { return e.classe === classeId; })
        .sort(function (a, b) { return (a.nom + a.prenom).localeCompare(b.nom + b.prenom, "fr"); });
    }

    function statutPaiement(pai) {
      var paye = montantPaye(pai);
      if (paye >= pai.total) return "Payé";
      if (paye <= 0) return "Impayé";
      return "Partiellement payé";
    }

    function montantPaye(pai) {
      return pai.paiements.reduce(function (s, p) { return s + p.montant; }, 0);
    }

    function dernierPaiement(pai) {
      if (!pai.paiements.length) return null;
      return pai.paiements[pai.paiements.length - 1];
    }

    /* Moyennes d'un élève : { parMatiere: [{matiereId, moyenne, coef}], generale, totalCoef } */
    function moyennesEleve(eleveId) {
      var el = getEleve(eleveId);
      if (!el) return { parMatiere: [], generale: 0, totalCoef: 0 };
      var ms = matieresDeClasse(el.classe);
      var parMatiere = [];
      ms.forEach(function (m) {
        var ns = notes
          .filter(function (x) { return x.eleveId === eleveId && x.matiereId === m.id; })
          .map(function (x) { return x.note; });
        if (!ns.length) return;
        var moy = ns.reduce(function (a, b) { return a + b; }, 0) / ns.length;
        parMatiere.push({ matiereId: m.id, matiere: m.nom, icone: m.icone, coef: m.coef, moyenne: Math.round(moy * 100) / 100 });
      });
      var num = parMatiere.reduce(function (s, p) { return s + p.moyenne * p.coef; }, 0);
      var coefs = parMatiere.reduce(function (s, p) { return s + p.coef; }, 0);
      var g = coefs ? num / coefs : 0;
      return { parMatiere: parMatiere, generale: Math.round(g * 100) / 100, totalCoef: coefs };
    }

    /* Classement dans la classe d'un élève (par moyenne générale) */
    function rangEleve(eleveId) {
      var el = getEleve(eleveId);
      if (!el) return null;
      // Vue réduite au périmètre du compte : l'API fournit le rang.
      if (el.rang) return el.rang;
      var camarades = elevesDeClasse(el.classe)
        .map(function (e) { return { id: e.id, moyenne: moyennesEleve(e.id).generale }; })
        .sort(function (a, b) { return b.moyenne - a.moyenne; });
      var pos = camarades.findIndex(function (c) { return c.id === eleveId; });
      return { rang: pos + 1, total: camarades.length };
    }

    function appreciation(moyenne) {
      if (moyenne >= 16) return { texte: "Excellent travail, félicitations ! Continuez ainsi.", mention: "Excellent" };
      if (moyenne >= 14) return { texte: "Très bon travail. Gardez ce niveau d'exigence.", mention: "Très bien" };
      if (moyenne >= 12) return { texte: "Bon travail. Quelques efforts supplémentaires vous mèneront très loin.", mention: "Bien" };
      if (moyenne >= 10) return { texte: "Travail passable. Des efforts restent à fournir dans certaines matières.", mention: "Assez bien" };
      if (moyenne >= 8) return { texte: "Résultats insuffisants, un sursaut d'effort est nécessaire.", mention: "Insuffisant" };
      return { texte: "Résultats très faibles. Un accompagnement régulier est indispensable.", mention: "Très insuffisant" };
    }

    function tauxPresence(eleveId) {
      var arr = presences.filter(function (p) { return p.eleveId === eleveId; });
      if (!arr.length) return 100;
      var abs = arr.filter(function (p) { return p.statut === "A"; }).length;
      return Math.round(((arr.length - abs) / arr.length) * 100);
    }

    /* Emploi du temps — grille déterministe par classe (même formule que le backend) */
    function emploiDuTemps(classeId) {
      var cls = getClasse(classeId);
      if (!cls) return [];
      var ids = matieresDeClasse(classeId).map(function (m) { return m.id; });
      // Rang de la classe dans la liste (pour décaler les cours)
      var shift = classes.findIndex(function (c) { return c.id === classeId; });
      var grid = [];
      JOURS.forEach(function (jour, j) {
        CRENEAUX.forEach(function (cr, ci) {
          // Créneau 3 vide mercredi et samedi (activités libres / sport)
          if ((ci === 2 && (j === 2 || j === 5))) return;
          var idx = (j + ci + shift) % ids.length;
          var mat = getMatiere(ids[idx]);
          var prof = enseignants.find(function (e) { return e.matiere === ids[idx]; });
          grid.push({
            classe: classeId,
            jour: jour,
            creneau: ci,
            heure: cr.label,
            matiere: mat ? mat.nom : "Étude",
            matiereId: ids[idx],
            enseignant: prof ? prof.nom + " " + prof.prenom : "—",
            salle: cls.salle + " / " + String(ci + 1)
          });
        });
      });
      return grid;
    }

    return {
      ecole: ecole,
      classes: classes,
      matieres: matieres,
      enseignants: enseignants,
      eleves: eleves,
      notes: notes,
      presences: presences,
      paiements: paiements,
      annonces: annonces,
      EVALS: EVALS,
      JOURS: JOURS,
      CRENEAUX: CRENEAUX,
      matieresDeClasse: matieresDeClasse,
      getClasse: getClasse,
      getMatiere: getMatiere,
      getEnseignant: getEnseignant,
      getEleve: getEleve,
      elevesDeClasse: elevesDeClasse,
      statutPaiement: statutPaiement,
      montantPaye: montantPaye,
      dernierPaiement: dernierPaiement,
      tauxPresence: tauxPresence,
      moyennesEleve: moyennesEleve,
      rangEleve: rangEleve,
      appreciation: appreciation,
      emploiDuTemps: emploiDuTemps
    };
  }

  // Fabrique publique — utilisée par js/live.js en mode API
  window.construireSD = construireSD;

  /* =========================================================
     DONNÉES DE DÉMONSTRATION (miroir historique du seed)
     ---------------------------------------------------------
     Désactivées par défaut : l'application démarre avec une base
     VIDE et n'affiche plus AUCUNE donnée fictive.
     Ce jeu n'est exécuté que si window.SM_DEMO_DATA === true est
     déclaré AVANT ce script (usage interne / vitrine uniquement).
     ========================================================= */

  if (window.SM_DEMO_DATA !== true) return; // base vide : aucune donnée fictive

  /* =========================================================
     ÉCOLE
     ========================================================= */
  var ecole = {
    nom: "Complexe Scolaire Privé Le Savoir",
    sigle: "CSP Le Savoir",
    slogan: "Éduquer, former, réussir",
    annee: "2026 – 2027",
    devise: "FCFA",
    telephone: "+226 25 40 12 34",
    email: "contact@lesavoir.edu",
    adresse: "Avenue de la Liberté, Ouagadougou — Burkina Faso",
    version: "1.0.0"
  };

  /* =========================================================
     CLASSES
     ========================================================= */
  var classes = [
    { id: "6A", nom: "6e A", cycle: "Collège", salle: "C-101", principal: "T002" },
    { id: "6B", nom: "6e B", cycle: "Collège", salle: "C-102", principal: "T002" },
    { id: "5A", nom: "5e A", cycle: "Collège", salle: "C-201", principal: "T004" },
    { id: "5B", nom: "5e B", cycle: "Collège", salle: "C-202", principal: "T004" },
    { id: "4A", nom: "4e A", cycle: "Collège", salle: "C-203", principal: "T003" },
    { id: "3A", nom: "3e A", cycle: "Collège", salle: "C-204", principal: "T001" },
    { id: "3B", nom: "3e B", cycle: "Collège", salle: "C-205", principal: "T005" },
    { id: "2A", nom: "2nde A", cycle: "Lycée", salle: "L-101", principal: "T006" },
    { id: "1A", nom: "1ère A", cycle: "Lycée", salle: "L-102", principal: "T006" },
    { id: "TA", nom: "Terminale A", cycle: "Lycée", salle: "L-201", principal: "T005" }
  ];

  /* =========================================================
     MATIÈRES
     ========================================================= */
  var matieres = [
    { id: "S1", nom: "Mathématiques", coef: 4, icone: "🧮", couleur: "blue" },
    { id: "S2", nom: "Français", coef: 4, icone: "📖", couleur: "green" },
    { id: "S3", nom: "Anglais", coef: 2, icone: "🌍", couleur: "cyan" },
    { id: "S4", nom: "SVT", coef: 2, icone: "🔬", couleur: "green" },
    { id: "S5", nom: "Histoire-Géographie", coef: 2, icone: "🗺️", couleur: "orange" },
    { id: "S6", nom: "Physique-Chimie", coef: 3, icone: "⚗️", couleur: "purple" },
    { id: "S7", nom: "EPS", coef: 1, icone: "🏃", couleur: "red" },
    { id: "S8", nom: "Philosophie", coef: 2, icone: "💭", couleur: "purple" }
  ];

  function matieresDeClasse(classeId) {
    var cls = getClasse(classeId);
    var base = ["S1", "S2", "S3", "S4", "S5", "S6", "S7"];
    var ids = cls && cls.cycle === "Lycée"
      ? ["S1", "S2", "S3", "S4", "S5", "S6", "S8", "S7"]
      : base;
    return matieres.filter(function (m) { return ids.indexOf(m.id) !== -1; });
  }

  /* =========================================================
     ENSEIGNANTS
     ========================================================= */
  var enseignants = [
    { id: "T001", nom: "Ouédraogo", prenom: "Jean", sexe: "M", tel: "70 11 22 33", email: "j.ouedraogo@lesavoir.edu", matiere: "S1", classes: ["3A", "3B"], statut: "Actif" },
    { id: "T002", nom: "Kaboré", prenom: "Salimata", sexe: "F", tel: "70 44 55 66", email: "s.kabore@lesavoir.edu", matiere: "S2", classes: ["6A", "6B", "5A", "5B", "4A"], statut: "Actif" },
    { id: "T003", nom: "Zongo", prenom: "Adama", sexe: "M", tel: "71 23 45 67", email: "a.zongo@lesavoir.edu", matiere: "S3", classes: ["3A", "3B", "4A", "2A"], statut: "Actif" },
    { id: "T004", nom: "Sawadogo", prenom: "Martine", sexe: "F", tel: "70 98 76 54", email: "m.sawadogo@lesavoir.edu", matiere: "S4", classes: ["3A", "3B", "5A", "5B"], statut: "Actif" },
    { id: "T005", nom: "Traoré", prenom: "Boureima", sexe: "M", tel: "72 12 34 56", email: "b.traore@lesavoir.edu", matiere: "S6", classes: ["3A", "3B", "2A", "1A", "TA"], statut: "Actif" },
    { id: "T006", nom: "Diallo", prenom: "Awa", sexe: "F", tel: "71 66 77 88", email: "a.diallo@lesavoir.edu", matiere: "S5", classes: ["2A", "1A", "TA", "4A"], statut: "Actif" },
    { id: "T007", nom: "Ouattara", prenom: "Lassina", sexe: "M", tel: "73 45 67 89", email: "l.ouattara@lesavoir.edu", matiere: "S7", classes: ["6A", "6B", "5A", "5B", "4A", "3A", "3B", "2A", "1A", "TA"], statut: "Actif" }
  ];

  /* =========================================================
     ÉLÈVES  (liste brute puis enrichie avec le parent)
     ========================================================= */
  var elevesBruts = [
    ["EL001", "Kaboré", "Paul", "M", "2009-04-12", "3A", "Actif"],
    ["EL002", "Ouédraogo", "Marie", "F", "2010-01-25", "4A", "Actif"],
    ["EL003", "Sawadogo", "Jean", "M", "2009-11-03", "3A", "Actif"],
    ["EL004", "Zongo", "Awa", "F", "2011-07-19", "5A", "Actif"],
    ["EL005", "Traoré", "Issa", "M", "2012-02-08", "6A", "Actif"],
    ["EL006", "Ouattara", "Fatou", "F", "2009-09-30", "3A", "Actif"],
    ["EL007", "Diallo", "Moussa", "M", "2010-05-14", "4A", "Inactif"],
    ["EL008", "Compaoré", "Aïcha", "F", "2008-03-22", "2A", "Actif"],
    ["EL009", "Ilboudo", "Abdoulaye", "M", "2007-12-01", "1A", "Actif"],
    ["EL010", "Nikiéma", "Salif", "M", "2010-08-17", "3B", "Actif"],
    ["EL011", "Bationo", "Prisca", "F", "2012-06-05", "6B", "Actif"],
    ["EL012", "Kafando", "Rachid", "M", "2010-03-11", "5B", "Actif"],
    ["EL013", "Rouamba", "Grâce", "F", "2006-04-17", "TA", "Actif"],
    ["EL014", "Sanou", "Alima", "F", "2009-06-23", "3A", "Actif"],
    ["EL015", "Dabiré", "Éric", "M", "2009-01-30", "3A", "Actif"]
  ];

  var prenomsParents = ["Moussa", "Aïssata", "Boureima", "Mariam", "Issouf", "Rasmata", "Seydou", "Fatoumata", "Adama", "Hawa", "Idrissa", "Kadidia", "Oumar", "Salimata", "Bakary"];
  var professions = ["Commerçant", "Enseignant", "Fonctionnaire", "Agriculteur", "Infirmier", "Technicien", "Commerçante", "Menuisier", "Secrétaire", "Transporteur"];

  var eleves = elevesBruts.map(function (r, i) {
    var idx = parseInt(r[0].replace("EL", ""), 10);
    var prenomParent = prenomsParents[(idx - 1) % prenomsParents.length];
    return {
      id: r[0],
      nom: r[1],
      prenom: r[2],
      sexe: r[3],
      naissance: r[4],
      classe: r[5],
      statut: r[6],
      inscription: "2020-09-" + String(10 + (i % 9)).padStart(2, "0"),
      parent: {
        nom: prenomParent + " " + r[1],
        lien: i % 2 === 0 ? "Père" : "Mère",
        tel: "70 " + String(10 + (idx * 3) % 40).padStart(2, "0") + " " + String(11 + (idx * 7) % 40).padStart(2, "0") + " " + String(22 + (idx * 5) % 40).padStart(2, "0"),
        email: (r[2] + "." + r[1]).toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "") + "@mail.com",
        profession: professions[idx % professions.length],
        adresse: ["Ouaga 2000", "Tampouy", "Karpala", "Dassasgho", "Pissy", "Gounghin"][idx % 6]
      }
    };
  });

  /* =========================================================
     NOTES — génération déterministe
     structure : { id, eleveId, classeId, matiereId, eval, note }
     ========================================================= */
  var notes = [];
  var EVALS = ["Devoir 1", "Devoir 2", "Composition"];

  eleves.forEach(function (el) {
    var matIds = matieresDeClasse(el.classe).map(function (m) { return m.id; });
    matIds.forEach(function (matId) {
      EVALS.forEach(function (ev, ei) {
        var n = parseInt(el.id.replace("EL", ""), 10);
        var seed = n * 100 + parseInt(matId.replace("S", ""), 10) * 10 + ei;
        var r = rand(seed);
        // Niveau « de l'élève » : base fixe + variation
        var base = 9 + (n % 6); // 9 à 14
        var note = Math.max(4, Math.min(19.5, Math.round((base + r * 5) * 2) / 2));
        notes.push({
          id: "N" + seed,
          eleveId: el.id,
          classeId: el.classe,
          matiereId: matId,
          eval: ev,
          note: note
        });
      });
    });
  });

  /* =========================================================
     PRÉSENCES — 12 semaines, générées de façon stable
     ========================================================= */
  var presences = [];
  var libPresence = { P: "Présent", R: "Retard", A: "Absent" };

  eleves.forEach(function (el, i) {
    var idx = parseInt(el.id.replace("EL", ""), 10);
    var debut = new Date(2026, 8, 7); // lundi 7 septembre 2026
    for (var s = 0; s < 12; s++) {
      var d = new Date(debut);
      d.setDate(debut.getDate() + s * 7);
      var st;
      if (i % 12 === s) st = "A";
      else if ((i * 5) % 12 === s) st = "R";
      else st = "P";
      presences.push({
        eleveId: el.id,
        date: d.toISOString().slice(0, 10),
        statut: st,
        libelle: libPresence[st]
      });
    }
  });

  function tauxPresence(eleveId) {
    var arr = presences.filter(function (p) { return p.eleveId === eleveId; });
    if (!arr.length) return 100;
    var abs = arr.filter(function (p) { return p.statut === "A"; }).length;
    return Math.round(((arr.length - abs) / arr.length) * 100);
  }

  /* =========================================================
     PAIEMENTS
     structure : { eleveId, motif, total, paiements: [{montant,date,mode}] }
     ========================================================= */
  var paiements = [];
  var MONTANTS = [60000, 50000, 40000];
  var DATES = ["2026-10-05", "2026-11-02", "2026-12-01"];
  var MODES = ["Espèces", "Mobile Money", "Chèque"];

  eleves.forEach(function (el, i) {
    var idx = parseInt(el.id.replace("EL", ""), 10);
    var cls = getClasse(el.classe);
    var total = cls && cls.cycle === "Lycée" ? 200000 : 150000;
    var regime = idx % 4; // 0 = tout payé, 1 = 2 versements, 2 = 1 versement, 3 = rien
    var versements = [];
    if (regime === 0) {
      MONTANTS.forEach(function (m, j) { versements.push({ montant: m, date: DATES[j], mode: MODES[j] }); });
    } else if (regime === 1) {
      versements.push({ montant: MONTANTS[0], date: DATES[0], mode: MODES[0] });
      versements.push({ montant: MONTANTS[1], date: DATES[1], mode: MODES[1] });
    } else if (regime === 2) {
      versements.push({ montant: MONTANTS[0], date: DATES[0], mode: MODES[0] });
    }
    paiements.push({ eleveId: el.id, motif: "Frais de scolarité " + ecole.annee, total: total, paiements: versements });
  });

  /* =========================================================
     ANNONCES
     ========================================================= */
  var annonces = [
    {
      id: "A1",
      titre: "Rentrée scolaire 2026-2027",
      contenu: "La rentrée scolaire aura lieu le lundi 5 octobre 2026 à 07h30 précises. Les élèves sont priés de venir avec leurs fournitures et leurs tenues complètes. Les parents sont attendus pour une rencontre d'information à 09h00.",
      categorie: "Information",
      date: "2026-09-05",
      auteur: "Administration",
      important: true
    },
    {
      id: "A2",
      titre: "Réunion des parents d'élèves",
      contenu: "Une réunion générale des parents d'élèves se tiendra le samedi 19 septembre 2026 dans la cour de l'école. Ordre du jour : résultats de l'année écoulée, règlement intérieur et projets de l'établissement pour cette nouvelle année.",
      categorie: "Réunion",
      date: "2026-09-12",
      auteur: "Comité de gestion",
      important: false
    },
    {
      id: "A3",
      titre: "Concours général de mathématiques",
      contenu: "Les élèves de 3e et de Terminale désireux de participer au concours général de mathématiques doivent s'inscrire auprès de M. Ouédraogo Jean avant le 30 septembre. Les épreuves se dérouleront en novembre.",
      categorie: "Concours",
      date: "2026-09-18",
      auteur: "Cellule pédagogique",
      important: false
    },
    {
      id: "A4",
      titre: "Rappel — Paiement des frais scolaires",
      contenu: "Nous rappelons aux parents que le paiement des frais de scolarité peut être effectué au secrétariat ou par Mobile Money. Un reçu vous sera remis pour chaque versement. Les élèves dont les frais ne sont pas soldés ne pourront pas composer aux examens.",
      categorie: "Finance",
      date: "2026-11-10",
      auteur: "Service financier",
      important: true
    }
  ];

  /* =========================================================
     EMPLOI DU TEMPS — généré à la demande par classe
     ========================================================= */
  var JOURS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi"];
  var CRENEAUX = [
    { label: "07h30 – 09h00", pause: false },
    { label: "09h00 – 10h30", pause: false },
    { label: "10h45 – 12h15", pause: true },   // mercredi après-midi libre
    { label: "15h00 – 16h30", pause: false }
  ];

  function emploiDuTemps(classeId) {
    var cls = getClasse(classeId);
    if (!cls) return [];
    var ids = matieresDeClasse(classeId).map(function (m) { return m.id; });
    // Rang de la classe dans la liste (pour décaler les cours)
    var shift = classes.findIndex(function (c) { return c.id === classeId; });
    var grid = [];
    JOURS.forEach(function (jour, j) {
      CRENEAUX.forEach(function (cr, ci) {
        // Créneau 3 vide mercredi et samedi (activités libres / sport)
        if ((ci === 2 && (j === 2 || j === 5))) return;
        var idx = (j + ci + shift) % ids.length;
        var mat = getMatiere(ids[idx]);
        var prof = enseignants.find(function (e) { return e.matiere === ids[idx]; });
        grid.push({
          classe: classeId,
          jour: jour,
          creneau: ci,
          heure: cr.label,
          matiere: mat ? mat.nom : "Étude",
          matiereId: ids[idx],
          enseignant: prof ? prof.nom + " " + prof.prenom : "—",
          salle: cls.salle + " / " + String(ci + 1)
        });
      });
    });
    return grid;
  }

  /* =========================================================
     HELPERS / ACCESSEURS
     ========================================================= */
  function getClasse(id) { return classes.find(function (c) { return c.id === id; }); }
  function getMatiere(id) { return matieres.find(function (m) { return m.id === id; }); }
  function getEnseignant(id) { return enseignants.find(function (e) { return e.id === id; }); }
  function getEleve(id) { return eleves.find(function (e) { return e.id === id; }); }

  function elevesDeClasse(classeId) {
    return eleves
      .filter(function (e) { return e.classe === classeId; })
      .sort(function (a, b) { return (a.nom + a.prenom).localeCompare(b.nom + b.prenom, "fr"); });
  }

  function statutPaiement(pai) {
    var paye = montantPaye(pai);
    if (paye >= pai.total) return "Payé";
    if (paye <= 0) return "Impayé";
    return "Partiellement payé";
  }

  function montantPaye(pai) {
    return pai.paiements.reduce(function (s, p) { return s + p.montant; }, 0);
  }

  function dernierPaiement(pai) {
    if (!pai.paiements.length) return null;
    return pai.paiements[pai.paiements.length - 1];
  }

  /* Moyennes d'un élève : { parMatiere: [{matiereId, moyenne, coef}], generale, totalCoef } */
  function moyennesEleve(eleveId) {
    var el = getEleve(eleveId);
    if (!el) return { parMatiere: [], generale: 0, totalCoef: 0 };
    var ms = matieresDeClasse(el.classe);
    var parMatiere = [];
    ms.forEach(function (m) {
      var ns = notes
        .filter(function (x) { return x.eleveId === eleveId && x.matiereId === m.id; })
        .map(function (x) { return x.note; });
      if (!ns.length) return;
      var moy = ns.reduce(function (a, b) { return a + b; }, 0) / ns.length;
      parMatiere.push({ matiereId: m.id, matiere: m.nom, icone: m.icone, coef: m.coef, moyenne: Math.round(moy * 100) / 100 });
    });
    var num = parMatiere.reduce(function (s, p) { return s + p.moyenne * p.coef; }, 0);
    var coefs = parMatiere.reduce(function (s, p) { return s + p.coef; }, 0);
    var g = coefs ? num / coefs : 0;
    return { parMatiere: parMatiere, generale: Math.round(g * 100) / 100, totalCoef: coefs };
  }

  /* Classement dans la classe d'un élève (par moyenne générale) */
  function rangEleve(eleveId) {
    var el = getEleve(eleveId);
    if (!el) return null;
    // Vue réduite au périmètre du compte : l'API fournit le rang.
    if (el.rang) return el.rang;
    var camarades = elevesDeClasse(el.classe)
      .map(function (e) { return { id: e.id, moyenne: moyennesEleve(e.id).generale }; })
      .sort(function (a, b) { return b.moyenne - a.moyenne; });
    var pos = camarades.findIndex(function (c) { return c.id === eleveId; });
    return { rang: pos + 1, total: camarades.length };
  }

  function appreciation(moyenne) {
    if (moyenne >= 16) return { texte: "Excellent travail, félicitations ! Continuez ainsi.", mention: "Excellent" };
    if (moyenne >= 14) return { texte: "Très bon travail. Gardez ce niveau d'exigence.", mention: "Très bien" };
    if (moyenne >= 12) return { texte: "Bon travail. Quelques efforts supplémentaires vous mèneront très loin.", mention: "Bien" };
    if (moyenne >= 10) return { texte: "Travail passable. Des efforts restent à fournir dans certaines matières.", mention: "Assez bien" };
    if (moyenne >= 8) return { texte: "Résultats insuffisants, un sursaut d'effort est nécessaire.", mention: "Insuffisant" };
    return { texte: "Résultats très faibles. Un accompagnement régulier est indispensable.", mention: "Très insuffisant" };
  }

})();
