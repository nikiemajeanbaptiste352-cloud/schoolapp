/* ============================================================
   SchoolManager — UI partagée
   Injection sidebar/topbar, modales, toasts, helpers
   ============================================================ */

(function () {
  "use strict";

  /* ---------- Pages du menu ----------
     La propriété « roles » n'est qu'un **repli** : elle sert uniquement si
     le serveur n'a pas fourni ses capacités (page ouverte hors ligne, ou
     ancienne version de l'API). En fonctionnement normal, c'est la liste
     `capacites.pages` renvoyée par `GET /api/v1/etat` qui décide — voir
     `backend/app/services/perimetre.py`. Y ajouter une page sans l'ajouter
     là-bas ne l'affichera pas. */
  var ROLES_TOUS = ["Administrateur", "Professeur", "Surveillant", "Élève", "Parent"];
  var PAGES = [
    { key: "dashboard", lien: "dashboard.html", icone: "🏠", titre: "Tableau de bord", groupe: "Général", roles: ROLES_TOUS },
    { key: "students", lien: "students.html", icone: "👨‍🎓", titre: "Élèves", groupe: "Gestion", roles: ROLES_TOUS },
    { key: "teachers", lien: "teachers.html", icone: "👨‍🏫", titre: "Enseignants", groupe: "Gestion", roles: ["Administrateur", "Professeur", "Surveillant"] },
    { key: "classes", lien: "classes.html", icone: "🏫", titre: "Classes", groupe: "Gestion", roles: ROLES_TOUS },
    { key: "subjects", lien: "subjects.html", icone: "📚", titre: "Matières", groupe: "Gestion", roles: ROLES_TOUS },
    { key: "grades", lien: "grades.html", icone: "📝", titre: "Notes", groupe: "Pédagogie", roles: ["Administrateur", "Professeur", "Élève", "Parent"] },
    { key: "report-cards", lien: "report-cards.html", icone: "📊", titre: "Bulletins", groupe: "Pédagogie", roles: ["Administrateur", "Professeur", "Élève", "Parent"] },
    { key: "timetable", lien: "timetable.html", icone: "📅", titre: "Emploi du temps", groupe: "Pédagogie", roles: ROLES_TOUS },
    { key: "mes-seances", lien: "mes-seances.html", icone: "✍️", titre: "Ma présence", groupe: "Espace enseignant", roles: ["Professeur"] },
    { key: "ma-paie", lien: "ma-paie.html", icone: "💵", titre: "Ma rémunération", groupe: "Espace enseignant", roles: ["Professeur"] },
    { key: "payments", lien: "payments.html", icone: "💰", titre: "Paiements", groupe: "Finance", roles: ["Administrateur", "Élève", "Parent"] },
    { key: "paie", lien: "paie.html", icone: "💶", titre: "Rémunérations", groupe: "Finance", roles: ["Administrateur"] },
    { key: "announcements", lien: "announcements.html", icone: "📢", titre: "Annonces", groupe: "Communication", roles: ROLES_TOUS },
    { key: "utilisateurs", lien: "utilisateurs.html", icone: "👥", titre: "Utilisateurs", groupe: "Système", roles: ["Administrateur"] },
    { key: "settings", lien: "settings.html", icone: "⚙️", titre: "Paramètres", groupe: "Système", roles: ROLES_TOUS }
  ];

  // Pages accessibles **hors menu** (liens internes). Elles n'ont pas de
  // restriction propre : elles dépendent de la page qui y mène
  // (`student-profile.html` est atteignable depuis une liste d'élèves déjà
  // filtrée par le serveur).
  var PAGES_HORS_MENU = ["student-profile"];

  /* ---------- Titres de l'interface ----------
     Un parent ne parle pas de « élèves » mais de ses enfants : le libellé
     s'adapte au rôle, la page et son contenu restent identiques. Seules les
     entrées qui changent réellement de sens figurent ici ; les autres gardent
     le titre de PAGES. */
  var LIBELLES_ROLE = {
    "Parent:students": "Mes enfants",
    "Élève:students": "Ma fiche",
    "Parent:classes": "Sa classe",
    "Élève:classes": "Ma classe",
    "Parent:subjects": "Ses matières",
    "Élève:subjects": "Mes matières",
    "Parent:timetable": "Son emploi du temps",
    "Élève:timetable": "Mon emploi du temps",
    "Parent:grades": "Ses notes",
    "Élève:grades": "Mes notes",
    "Parent:report-cards": "Ses bulletins",
    "Élève:report-cards": "Mes bulletins",
    "Parent:payments": "Mes paiements",
    "Élève:payments": "Mes paiements",
    "Professeur:grades": "Saisie des notes"
  };

  var ROLE_EMOJI = { Administrateur: "👨‍💼", Professeur: "👨‍🏫", Surveillant: "📋", Élève: "👨‍🎓", Parent: "👨‍👩‍👧" };

  /* ---------- Capacités renvoyées par le serveur ----------
     `js/live.js` place ici la réponse de `GET /api/v1/etat` AVANT de charger
     ce fichier : le menu et la garde des pages n'ont donc rien à deviner. */
  function capacites() {
    return window.SM_CAPACITES || null;
  }

  function roleCourant() {
    var c = capacites();
    if (c && c.role) return c.role;
    var s = getSession();
    return s ? s.role : null;
  }

  function porteeEleves() {
    var c = capacites();
    return (c && c.portee) || "tous";
  }

  // Le compte a-t-il le droit d'effectuer cette opération d'écriture ?
  // (liste fermée : sans capacités, la réponse est NON)
  function peut(operation) {
    var c = capacites();
    if (!c || !c.operations) return false;
    return c.operations.indexOf(operation) !== -1;
  }

  // Libellé d'une page pour le rôle courant.
  function titrePage(key, defaut) {
    var r = roleCourant();
    return (r && LIBELLES_ROLE[r + ":" + key]) || defaut;
  }

  /* ---------- Fiche enseignant du compte connecté ----------
     Un professeur est identifié par l'adresse de son compte, déjà présente
     dans `enseignants` de `/etat` (l'annuaire est servi au personnel). Sert à
     signaler « mes classes » / « ma matière » sans rien retirer de la vue
     complète que le serveur accorde par ailleurs. `null` si le compte n'est
     rattaché à aucune fiche : l'appelant garde alors la vue générale. */
  function monEnseignant(sd) {
    var moi = window.SM_MOI || {};
    var liste = (sd || window.SD || {}).enseignants;
    if (!moi.email || !liste || !liste.length) return null;
    var email = String(moi.email).toLowerCase();
    for (var i = 0; i < liste.length; i++) {
      if (String(liste[i].email || "").toLowerCase() === email) return liste[i];
    }
    return null;
  }

  /* ---------- Session ---------- */
  function getSession() {
    try {
      return JSON.parse(sessionStorage.getItem("sm_session") || "null");
    } catch (e) { return null; }
  }

  var TITRES = {};
  PAGES.forEach(function (p) { TITRES[p.key] = p.titre; });
  TITRES["student-profile"] = "Fiche élève";

  /* ---------- Libellé du mode de données (toujours le serveur) ---------- */
  function modeApi() { return window.SM_MODE === "api"; }
  function modeLabel() { return "API"; }
  function chipMode() { return modeApi() ? "🔌 Données du serveur" : ""; }

  /* ---------- Construction du layout ---------- */
  function buildLayout() {
    var page = document.body.getAttribute("data-page");

    // Garde d'authentification (sauf page de connexion)
    if (document.body.dataset.auth === "true" && !getSession()) {
      window.location.replace("../index.html");
      return;
    }

    // Garde de périmètre : une page que le rôle effectif n'a pas le droit
    // d'ouvrir renvoie au tableau de bord. Avant la Phase 2, ce contrôle
    // n'existait qu'au moment d'une bascule d'établissement : il suffisait
    // de saisir l'adresse d'une page pour l'afficher (les données restaient
    // protégées par l'API, mais l'écran s'ouvrait).
    if (page && !pageAutorisee(page, roleCourant())) {
      try { sessionStorage.setItem("sm_flash", "Cette page n'est pas accessible avec votre profil."); } catch (e) { /* stockage indisponible */ }
      window.location.replace("dashboard.html");
      return;
    }

    // Rôle effectif + liste des pages autorisées, tels que décidés par le
    // serveur (`GET /api/v1/etat` → `capacites`). Si le serveur n'a rien
    // fourni, on retombe sur la propriété « roles » — repli uniquement.
    var sessionRole = roleCourant();
    var pagesServeur = pagesAutoriseesServeur();

    var sidebar = document.getElementById("sidebar");
    var topbar = document.getElementById("topbar");
    if (!sidebar && !topbar) return;

    // Sidebar
    if (sidebar) {
      var nav = "";
      var lastGroupe = "";
      PAGES.forEach(function (p) {
        // Liste fermée : uniquement ce que le serveur a autorisé.
        if (pagesServeur) {
          if (pagesServeur.indexOf(p.key) === -1) return;
        } else if (p.roles && p.roles.indexOf(sessionRole) === -1) {
          return;
        }
        if (p.groupe !== lastGroupe) {
          nav += '<div class="nav-section">' + p.groupe + "</div>";
          lastGroupe = p.groupe;
        }
        var act = page === p.key ? " active" : "";
        nav += '<a class="nav-link' + act + '" href="' + p.lien + '"><span class="nav-ico">' + p.icone + "</span>" + escapeHtml(titrePage(p.key, p.titre)) + "</a>";
      });
      var versionTexte = SD.ecole.version ? "<span>v" + SD.ecole.version + "</span>" : "<span></span>";
      sidebar.innerHTML =
        '<div class="sidebar-head">' +
        '  <img class="brand-logo" src="../assets/logo.svg" alt="Logo">' +
        '  <div><div class="brand-name">SchoolManager</div><div class="brand-sub">Gestion scolaire</div></div>' +
        "</div>" +
        '<nav class="sidebar-nav">' + nav + "</nav>" +
        '<div class="sidebar-foot">' + versionTexte + '<span class="pill-demo">' + modeLabel() + "</span></div>";
    }

    // Topbar
    if (topbar) {
      // Identité : le serveur fait foi (`capacites.role`, `moi`) ;
      // sessionStorage n'est qu'un repli d'affichage.
      var sess = getSession();
      var moi = window.SM_MOI || {};
      var role = roleCourant() || (sess ? sess.role : "Administrateur");
      var name = moi.nom || (sess ? sess.nom : "Administrateur");
      var email = moi.email || (sess ? sess.email : "");
      var emoji = ROLE_EMOJI[role] || "👤";
      var titre = titrePage(page, TITRES[page] || "SchoolManager");

      // Les annonces ne sont proposées qu'aux profils qui possèdent la page.
      var voitAnnonces = !pagesServeur || pagesServeur.indexOf("announcements") !== -1;
      var notifs = voitAnnonces ? SD.annonces.slice(0, 3).map(function (a) {
        return '<button class="dropdown-item" data-go="announcements"><span>📢</span>' + escapeHtml(a.titre) + "</button>";
      }).join("") : "";

      topbar.innerHTML =
        '<div class="topbar-left">' +
        '  <button class="btn-icon menu-btn" id="btnMenu" title="Menu">☰</button>' +
        '  <h1 class="page-title">' + titre + "</h1>" +
        "</div>" +
        '<div class="topbar-right">' +
        (chipMode() ? '  <span class="demo-chip">' + chipMode() + "</span>" : "") +
        '  <div class="dropdown" id="dropEcole" style="display:none">' +
        '    <button class="ecole-chip" id="btnEcole" title="Changer d\u2019établissement">' +
        '      <span>🏫</span><span class="ecole-nom" id="ecoleNom">' + escapeHtml(ecoleCourante()) + '</span><span class="ecole-chev">▼</span>' +
        "    </button>" +
        '    <div class="dropdown-menu" id="menuEcole"></div>' +
        "  </div>" +
        '  <div class="dropdown">' +
        '    <button class="btn-icon" id="btnNotif" title="Notifications">🔔<span class="notif-dot"></span></button>' +
        '    <div class="dropdown-menu" id="menuNotif">' +
        '      <div class="dropdown-head">Notifications</div>' +
        notifs +
        (voitAnnonces ? '      <div class="dropdown-sep"></div>' +
        '      <button class="dropdown-item" data-go="announcements"><span>🔔</span>Toutes les annonces</button>' : "") +
        "    </div>" +
        "  </div>" +
        '  <div class="dropdown">' +
        '    <button class="user-chip" id="btnUser" title="Mon compte">' +
        '      <span class="avatar" style="background:' + couleurAvatar(name) + '">' + initiales(name) + "</span>" +
        '      <span class="u-info"><span class="u-name" style="display:block">' + escapeHtml(name) + '</span><span class="u-role">' + escapeHtml(role) + "</span></span>" +
        "    </button>" +
        '    <div class="dropdown-menu" id="menuUser" style="right:0">' +
        '      <div class="dropdown-head">' + emoji + " Compte" + (email ? " · " + escapeHtml(email) : "") + "</div>" +
        '      <button class="dropdown-item" data-go="settings"><span>⚙️</span>Paramètres</button>' +
        '      <div class="dropdown-sep"></div>' +
        '      <button class="dropdown-item danger" id="btnLogout"><span>🚪</span>Se déconnecter</button>' +
        "    </div>" +
        "  </div>" +
        "</div>";

      // Événements topbar
      var btnMenu = document.getElementById("btnMenu");
      if (btnMenu) btnMenu.addEventListener("click", function () { document.body.classList.toggle("sidebar-open"); });
      var btnNotif = document.getElementById("btnNotif");
      if (btnNotif) btnNotif.addEventListener("click", function (e) { e.stopPropagation(); toggleDropdown("menuNotif"); });
      var btnUser = document.getElementById("btnUser");
      if (btnUser) btnUser.addEventListener("click", function (e) { e.stopPropagation(); toggleDropdown("menuUser"); });
      var btnEcole = document.getElementById("btnEcole");
      if (btnEcole) btnEcole.addEventListener("click", function (e) { e.stopPropagation(); toggleDropdown("menuEcole"); });
      chargerEcoles();
      var btnLogout = document.getElementById("btnLogout");
      if (btnLogout) btnLogout.addEventListener("click", function () {
        // Déconnexion : efface le jeton API (si présent) puis la session
        if (window.API) window.API.deconnexion();
        sessionStorage.removeItem("sm_session");
        window.location.replace("../index.html");
      });
      // Clic ailleurs : fermer menus + sidebar
      document.addEventListener("click", function (e) {
        if (!e.target.closest(".dropdown")) closeDropdowns();
        if (document.body.classList.contains("sidebar-open") && !e.target.closest(".sidebar")) {
          document.body.classList.remove("sidebar-open");
        }
      });
      // Navigation depuis les items de menu déroulant
      document.querySelectorAll("[data-go]").forEach(function (b) {
        b.addEventListener("click", function () {
          window.location.href = b.getAttribute("data-go") === "settings" ? "settings.html" : "announcements.html";
        });
      });
    }

    // Actions interdites : masquées. On masque au lieu de retirer, car les
    // scripts de page attachent leurs écouteurs à ces boutons au chargement.
    appliquerCapacites();

    // Titre de l'écran et de l'onglet adaptés au rôle (« Mes enfants » pour un
    // parent). Les libellés génériques ne sont pas touchés : seuls ceux qui
    // varient selon le rôle sont réécrits.
    var libelleRole = titrePage(page, null);
    if (libelleRole) {
      var h2 = document.querySelector(".page-header h2");
      if (h2) {
        var ico = iconePage(page);
        h2.textContent = (ico ? ico + " " : "") + libelleRole;
      }
      document.title = libelleRole + " — SchoolManager";
    }

    // Contenu de l'écran adapté au rôle (sous-titre, filtres sans objet).
    adapterPageAuRole(page);

    // Message différé (ex. bascule d'établissement) : la bascule recharge la
    // page, le message est donc affiché au chargement suivant.
    var flash = null;
    try {
      flash = sessionStorage.getItem("sm_flash");
      if (flash) sessionStorage.removeItem("sm_flash");
    } catch (e) { /* stockage indisponible */ }
    if (flash) toast(escapeHtml(flash), "success");

    // Micro-animations (apparitions, compteurs, onde au clic)
    animerInterface();
  }

  /* ---------- Actions autorisées ----------
     Tout élément portant `data-cap="<opération>"` est masqué si le rôle
     effectif n'a pas cette opération (voir OPERATIONS_PAR_ROLE dans
     backend/app/services/perimetre.py). L'API reste la seule juge : ceci
     n'évite pas un appel direct, cela évite de proposer l'action. */
  function appliquerCapacites() {
    var liste = document.querySelectorAll("[data-cap]");
    for (var i = 0; i < liste.length; i++) {
      var op = liste[i].getAttribute("data-cap");
      if (op && !peut(op)) liste[i].style.display = "none";
    }
  }

  function iconePage(key) {
    for (var i = 0; i < PAGES.length; i++) {
      if (PAGES[i].key === key) return PAGES[i].icone;
    }
    return "";
  }

  /* ---------- Contenu des pages selon le rôle ----------
     Une même page ne rend pas le même service à tout le monde. Un parent qui
     ouvre « Élèves » ne gère pas l'établissement : il consulte son enfant.
     Le serveur décide ce qui est VISIBLE (capacités) ; on adapte ici ce qui
     est DIT — sous-titre, filtres inutiles — pour que chaque page parle de la
     fonction réelle du profil qui la lit.

     Une page absente de cette table garde son texte d'origine (valable pour
     tous les rôles qui y accèdent). */
  var TEXTES_PAGES = {
    dashboard: {
      Administrateur: "Vue d'ensemble de l'établissement : effectifs, classes et présence.",
      Professeur: "Vos classes, vos matières et votre activité pédagogique.",
      Surveillant: "Vie scolaire : effectifs, classes et suivi des présences.",
      "Élève": "Votre scolarité : moyenne, présences, paiements et annonces.",
      Parent: "La scolarité de votre enfant : notes, présences et paiements."
    },
    students: {
      Administrateur: "Gérez les fiches de tous les élèves de l'établissement.",
      Professeur: "Les élèves de l'établissement — vous notez ceux de vos classes.",
      Surveillant: "Les élèves de l'établissement — suivi de la vie scolaire.",
      "Élève": "Votre fiche d'élève et votre parcours scolaire.",
      Parent: "Les fiches de vos enfants inscrits dans l'établissement."
    },
    teachers: {
      Administrateur: "Gérez l'équipe pédagogique, les matières et les barèmes horaires.",
      Professeur: "L'équipe pédagogique — votre fiche est signalée.",
      Surveillant: "Annuaire de l'équipe pédagogique."
    },
    classes: {
      Administrateur: "Gérez les classes, les niveaux et les professeurs principaux.",
      Professeur: "Les classes de l'établissement — vos classes sont signalées.",
      Surveillant: "Les classes de l'établissement."
    },
    subjects: {
      Administrateur: "Gérez les matières, leurs coefficients et leurs enseignants.",
      Professeur: "Les matières de l'établissement — la vôtre est signalée.",
      Surveillant: "Les matières enseignées dans l'établissement."
    },
    grades: {
      Administrateur: "Saisissez et consultez les notes de toutes les classes.",
      Professeur: "Saisissez les notes de vos classes, par évaluation.",
      "Élève": "Vos notes, matière par matière et évaluation par évaluation.",
      Parent: "Les notes de votre enfant, par matière et par évaluation."
    },
    "report-cards": {
      Administrateur: "Consultez et imprimez les bulletins de l'établissement.",
      Professeur: "Les bulletins des classes où vous enseignez.",
      "Élève": "Votre bulletin scolaire, prêt à imprimer.",
      Parent: "Les bulletins de votre enfant, prêts à imprimer."
    },
    timetable: {
      Administrateur: "Emploi du temps des classes et des enseignants.",
      Professeur: "Votre emploi du temps et celui de vos classes.",
      Surveillant: "Emploi du temps des classes.",
      "Élève": "Votre emploi du temps de la semaine.",
      Parent: "L'emploi du temps de votre enfant."
    },
    payments: {
      Administrateur: "Suivez les frais de scolarité, les encaissements et les impayés.",
      "Élève": "Vos frais de scolarité, vos versements et votre solde.",
      Parent: "Les frais de scolarité de votre enfant, vos versements et le solde."
    },
    paie: {
      Administrateur: "Rémunérations des enseignants, barèmes horaires et fiches de paie."
    },
    announcements: {
      Administrateur: "Publiez et gérez les annonces de l'établissement.",
      Professeur: "Les annonces de l'établissement.",
      Surveillant: "Les annonces de l'établissement.",
      "Élève": "Les annonces de l'établissement.",
      Parent: "Les annonces de l'établissement."
    },
    utilisateurs: {
      Administrateur: "Comptes, rôles et rattachements à cet établissement."
    },
    // Page hors menu : le texte d'origine convient au personnel, on ne le
    // réécrit que pour les profils qui voient un dossier plus étroit que la
    // fiche complète (onglets filtrés par ACCES_ONGLETS).
    "student-profile": {
      Professeur: "Le dossier pédagogique de l'élève : notes, présences et bulletin.",
      Surveillant: "Le suivi de vie scolaire de l'élève : présences et contact du parent.",
      "Élève": "Votre dossier scolaire : notes, présences, paiements et bulletin.",
      Parent: "Le dossier scolaire de votre enfant : notes, présences, paiements et bulletin."
    },
    settings: {
      Administrateur: "Informations de l'établissement, comptes et préférences.",
      Professeur: "Votre profil et vos préférences.",
      Surveillant: "Votre profil et vos préférences.",
      "Élève": "Votre profil et vos préférences.",
      Parent: "Votre profil et vos préférences."
    }
  };

  /* Adaptation de l'écran au rôle : texte d'en-tête, filtres sans objet. */
  function adapterPageAuRole(page) {
    page = page || document.body.getAttribute("data-page");
    if (!page) return;
    var role = roleCourant();

    // 1. Sous-titre : ce que la page permet de faire POUR ce profil.
    var textes = TEXTES_PAGES[page];
    if (textes) {
      var texte = textes[role] || textes.defaut;
      if (texte) {
        var sub = document.querySelector(".page-header .subtitle");
        if (sub) sub.textContent = texte;
      }
    }

    // 2. Périmètre réduit (élève, parent) : la liste ne contient que son
    //    dossier. Un moteur de recherche n'y sert à rien, on le retire.
    if (porteeEleves() !== "tous") {
      var boites = document.querySelectorAll(".page-header .search-box");
      for (var i = 0; i < boites.length; i++) boites[i].style.display = "none";
    }

    // 3. Étiquette du profil sur le corps de page : sert au CSS et au
    //    diagnostic (inspecter data-role suffit à savoir qui a rendu la page).
    document.body.setAttribute("data-role", role || "");
  }

  /* ---------- V2 : micro-animations ----------
     Purement décoratives et progressives : si le navigateur ne sait pas
     faire (ou si l'utilisateur a demandé moins d'animations), l'interface
     reste exactement fonctionnelle. */
  var MOUVEMENT_REDUIT = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  var SEL_APPARITION = ".hero-banner, .page-header, .card, .stat-card, .table-wrap, .announce-card, .settings-sec, .print-area, .class-card, .profile-head";
  var obsAnim = null;
  var animationsPretes = false;

  // L'élément est-il déjà dans un bloc animé ? (évite les animations imbriquées)
  function dansCible(el) {
    var p = el.parentElement;
    while (p && p !== document.body) {
      if (p.matches && p.matches(SEL_APPARITION)) return true;
      p = p.parentElement;
    }
    return false;
  }

  function estVisible(el) {
    return !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  }

  // Peut-on animer ce texte ? (nombres simples, éventuellement « % » ou « FCFA »)
  function estAnimable(el) {
    var t = String(el.textContent || "");
    if (t.replace(/FCFA/g, "").replace(/[0-9\s\u202f\u00a0%]/g, "") !== "") return false;
    var n = t.replace(/[^0-9]/g, "");
    return n.length > 0 && n.length <= 7;
  }

  // Compteur qui « monte » jusqu'à la valeur affichée
  function animerNombre(el) {
    if (!estAnimable(el) || !window.requestAnimationFrame) return;
    var texte = String(el.textContent || "");
    var cible = parseInt(texte.replace(/[^0-9]/g, ""), 10);
    if (!cible) return;
    var premier = texte.search(/[0-9]/);
    var dernier = texte.length - 1 - texte.split("").reverse().join("").search(/[0-9]/);
    var prefixe = texte.slice(0, premier);
    var suffixe = texte.slice(dernier + 1);
    var groupe = /[\u202f\u00a0 ]/.test(texte.slice(premier, dernier + 1));
    function format(n) {
      var s = String(n);
      return groupe ? s.replace(/\B(?=(\d{3})+(?!\d))/g, "\u202f") : s;
    }
    var debut = null;
    var duree = 950;
    el.textContent = prefixe + format(0) + suffixe;
    function image(t) {
      if (debut === null) debut = t;
      var p = Math.min(1, (t - debut) / duree);
      var e = 1 - Math.pow(1 - p, 3);
      el.textContent = prefixe + format(Math.round(cible * e)) + suffixe;
      if (p < 1) window.requestAnimationFrame(image);
      else el.textContent = texte;
    }
    window.requestAnimationFrame(image);
  }

  function reveler(el) {
    if (el.getAttribute("data-sm-cnt")) {
      el.removeAttribute("data-sm-cnt");
      animerNombre(el);
    } else {
      el.classList.add("sm-in");
    }
  }

  function suivantEntree(liste) {
    for (var i = 0; i < liste.length; i++) {
      var el = liste[i].target;
      if (obsAnim) obsAnim.unobserve(el);
      reveler(el);
    }
  }

  function creerObservateur() {
    if (obsAnim) return obsAnim;
    if (!("IntersectionObserver" in window)) return null;
    obsAnim = new window.IntersectionObserver(suivantEntree, {
      threshold: 0,
      rootMargin: "0px 0px -6% 0px"
    });
    return obsAnim;
  }

  // Apparition des blocs au défilement (une seule fois par bloc)
  function preparerApparitions() {
    var obs = creerObservateur();
    if (!obs) return;
    var h = window.innerHeight || document.documentElement.clientHeight || 800;
    var liste = document.querySelectorAll(SEL_APPARITION);
    var n = 0;
    for (var i = 0; i < liste.length; i++) {
      var el = liste[i];
      if (el.getAttribute("data-sm-rv")) continue;
      if (dansCible(el)) continue;
      // Un bloc contenant une modale ne doit jamais être transformé :
      // cela casserait le positionnement des fenêtres (position: fixed).
      if (el.querySelector(".modal-overlay")) continue;
      if (!estVisible(el)) continue;
      var r = el.getBoundingClientRect();
      var deja = r.top < h * 0.94 && r.bottom > 0;
      el.setAttribute("data-sm-rv", "1");
      el.classList.add("sm-rv");
      el.style.setProperty("--sm-d", deja ? "0ms" : Math.min(n, 7) * 55 + "ms");
      n++;
      if (deja) {
        // Déjà à l'écran : apparition immédiate, décalage géré en JS.
        revelerDiffere(el, Math.min(n, 7) * 55);
      } else {
        obs.observe(el);
      }
    }
  }

  function revelerDiffere(el, delai) {
    if (delai > 0) {
      setTimeout(function () { reveler(el); }, delai);
    } else if (window.requestAnimationFrame) {
      window.requestAnimationFrame(function () { reveler(el); });
    } else {
      reveler(el);
    }
  }

  // Filet de sécurité : si l'observateur ne s'est jamais déclenché
  // (onglet en arrière-plan, navigateur limité), on révèle tout.
  function securiteApparitions() {
    if (document.querySelector(".sm-rv.sm-in")) return;
    var liste = document.querySelectorAll(".sm-rv:not(.sm-in)");
    for (var i = 0; i < liste.length; i++) liste[i].classList.add("sm-in");
  }

  // Compteurs animés des cartes de statistiques
  function preparerCompteurs() {
    var liste = document.querySelectorAll(".stat-value, .mini-stat .v");
    for (var i = 0; i < liste.length; i++) {
      var el = liste[i];
      if (el.getAttribute("data-sm-fait") || !estVisible(el) || !estAnimable(el)) continue;
      el.setAttribute("data-sm-fait", "1");
      var obs = creerObservateur();
      if (obs) {
        el.setAttribute("data-sm-cnt", "1");
        obs.observe(el);
      } else {
        animerNombre(el);
      }
    }
  }

  function preparerAnimations() {
    if (MOUVEMENT_REDUIT) return;
    preparerApparitions();
    preparerCompteurs();
  }

  // Onde au clic sur les boutons
  function ondeClic(e) {
    var b = e.target && e.target.closest ? e.target.closest(".btn, .quick-btn") : null;
    if (!b || b.disabled) return;
    var r = b.getBoundingClientRect();
    var d = Math.max(r.width, r.height, 24);
    var cx = e.clientX ? e.clientX : r.left + r.width / 2;
    var cy = e.clientY ? e.clientY : r.top + r.height / 2;
    var s = document.createElement("span");
    s.className = "sm-onde";
    s.style.width = d + "px";
    s.style.height = d + "px";
    s.style.left = Math.round(cx - r.left - d / 2) + "px";
    s.style.top = Math.round(cy - r.top - d / 2) + "px";
    b.appendChild(s);
    setTimeout(function () {
      if (s.parentNode) s.parentNode.removeChild(s);
    }, 650);
  }

  // Barre de progression en haut de page pendant un changement de page
  function barreCharge() {
    var b = document.getElementById("smCharge");
    if (!b) {
      b = document.createElement("div");
      b.id = "smCharge";
      document.body.appendChild(b);
    }
    b.classList.remove("sm-charge-on");
    void b.offsetWidth; // force le redémarrage de l'animation
    b.classList.add("sm-charge-on");
    setTimeout(function () { b.classList.remove("sm-charge-on"); }, 1600);
  }

  function lienCharge(e) {
    var a = e.target && e.target.closest ? e.target.closest("a[href]") : null;
    if (!a) return;
    var h = a.getAttribute("href") || "";
    if (!h || h.charAt(0) === "#" || a.target === "_blank") return;
    if (/^(mailto:|tel:|https?:|javascript:)/i.test(h)) return;
    barreCharge();
  }

  function animerInterface() {
    if (animationsPretes) return;
    animationsPretes = true;
    preparerAnimations();
    // Les pages remplissent leurs conteneurs juste après ui.js :
    // on repasse quelques fois pour rattraper le contenu tardif.
    setTimeout(preparerAnimations, 600);
    setTimeout(preparerAnimations, 1600);
    setTimeout(securiteApparitions, 3000);
    if (window.addEventListener) {
      window.addEventListener("load", function () { setTimeout(preparerAnimations, 60); });
    }
    if (MOUVEMENT_REDUIT) return;
    document.addEventListener("click", ondeClic);
    document.addEventListener("click", lienCharge);
  }

  /* ---------- Sélecteur d'établissement (Phase 3 — rattachement) ---------- */
  // École affichée : mémorisée à la bascule, sinon celle du bootstrap SD.
  function ecoleCourante() {
    var s = getSession();
    if (s && s.ecole) return s.ecole;
    if (window.SD && SD.ecole) return SD.ecole.sigle || SD.ecole.nom || "";
    return "";
  }

  /* ---------- Contrôle d'accès aux pages ----------
     Deux sources, dans cet ordre :
       1. `capacites().pages` — la liste décidée par le serveur (elle découle
          des `require_roles(...)` des routeurs, voir perimetre.py) ;
       2. la propriété « roles » de PAGES — repli local, utilisé quand le
          serveur n'a rien fourni ou quand on évalue un autre rôle que le
          rôle courant (bascule d'établissement).
     La liste est FERMÉE : une clé inconnue est refusée. Auparavant elle était
     acceptée, si bien qu'un simple `sessionStorage` modifié à la main
     contournait le menu. */
  var PAGES_MINIMALES = ["dashboard", "settings"];

  function pagesAutoriseesServeur() {
    var c = capacites();
    return c && c.pages ? c.pages : null;
  }

  function pagesPourRole(role) {
    var c = capacites();
    if (c && c.pages && role && role === c.role) return c.pages;
    var liste = [];
    if (role) {
      PAGES.forEach(function (p) {
        if (p.roles && p.roles.indexOf(role) !== -1) liste.push(p.key);
      });
    }
    return liste;
  }

  // La page courante est-elle visible pour ce rôle ?
  function pageAutorisee(cle, role) {
    if (!cle) return true;
    // Toujours autorisées : sans cela, la redirection reboucle sur dashboard.
    if (PAGES_MINIMALES.indexOf(cle) !== -1) return true;
    var liste = pagesPourRole(role);
    if (liste.indexOf(cle) !== -1) return true;
    // Écran hors menu (fiche élève) : suit la page qui y mène.
    if (PAGES_HORS_MENU.indexOf(cle) !== -1) return liste.indexOf("students") !== -1;
    return false;
  }

  // Récupère les rattachements du compte. Le sélecteur n'apparaît que si le
  // compte est rattaché à plusieurs établissements (sinon inutile).
  function chargerEcoles() {
    if (!window.API || !window.API.mesEcoles) return;
    window.API.mesEcoles().then(function (liste) {
      var ecoles = liste || [];
      if (ecoles.length <= 1) return; // un seul établissement : rien à basculer
      var menu = document.getElementById("menuEcole");
      var drop = document.getElementById("dropEcole");
      var nom = document.getElementById("ecoleNom");
      if (!menu || !drop) return;
      if (nom) nom.textContent = ecoleCourante();

      var html = '<div class="dropdown-head">Mes établissements</div>';
      ecoles.forEach(function (e) {
        var libelle = e.sigle || e.nom || ("École " + e.school_id);
        var bloque = e.statut !== "actif";
        var sous = bloque
          ? (e.statut === "invite" ? "Invitation en attente" : "Rattaché (suspendu)")
          : e.role + (e.active ? " • école affichée" : "");
        html +=
          '<button class="dropdown-item ecole-item' + (e.active ? " actif" : "") + '"' +
          ' data-ecole="' + e.school_id + '"' + (bloque ? " disabled" : "") + ">" +
          "<span>🏫</span>" +
          '<span class="ecole-txt"><span class="ecole-n">' + escapeHtml(libelle) + "</span>" +
          '<span class="ecole-r">' + escapeHtml(sous) + "</span></span>" +
          (e.active ? '<span class="coche">✓</span>' : "") +
          "</button>";
      });
      menu.innerHTML = html;

      menu.querySelectorAll("[data-ecole]").forEach(function (b) {
        b.addEventListener("click", function () {
          basculerVers(parseInt(b.getAttribute("data-ecole"), 10));
        });
      });
      drop.style.display = "";
    }).catch(function () {
      // Serveur injoignable ou compte non rattaché : sélecteur masqué.
    });
  }

  // Bascule : le backend renvoie un NOUVEAU jeton (rôle de l'école visée) ;
  // api.js l'a déjà mémorisé, on met à jour sm_session puis on recharge.
  function basculerVers(schoolId) {
    if (!schoolId || !window.API || !window.API.basculerEcole) return;
    window.API.basculerEcole(schoolId).then(function (data) {
      var s = getSession() || {};
      var u = (data && data.user) || {};
      if (u.role) s.role = u.role;
      if (u.nom) s.nom = u.nom;
      if (u.email) s.email = u.email;
      if (data && data.ecole) s.ecole = data.ecole;
      try { sessionStorage.setItem("sm_session", JSON.stringify(s)); } catch (e) { /* stockage indisponible */ }
      if (data && data.ecole) {
        try { sessionStorage.setItem("sm_flash", "Établissement : " + data.ecole); } catch (e2) { /* stockage indisponible */ }
      }
      setTimeout(function () {
        // La page ouverte peut être réservée au rôle précédent (ex. l'espace
        // enseignant) : on revient au tableau de bord plutôt que de laisser
        // la garde de cette page renvoyer l'utilisateur à la connexion.
        var cle = document.body.getAttribute("data-page");
        if (cle && !pageAutorisee(cle, s.role)) window.location.href = "dashboard.html";
        else window.location.reload();
      }, 500);
    }).catch(function (err) {
      toast(escapeHtml((err && err.detail) || "Bascule d'établissement impossible."), "error");
    });
  }

  /* ---------- Menus déroulants ---------- */
  function toggleDropdown(id) {
    var m = document.getElementById(id);
    if (!m) return;
    var open = m.classList.contains("open");
    closeDropdowns();
    if (!open) m.classList.add("open");
  }
  function closeDropdowns() {
    document.querySelectorAll(".dropdown-menu.open").forEach(function (m) { m.classList.remove("open"); });
  }

  /* ---------- Helpers texte ---------- */
  function escapeHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function initiales(nom) {
    var parts = String(nom || "?").trim().split(/\s+/);
    var i1 = parts[0] ? parts[0][0] : "";
    var i2 = parts.length > 1 ? parts[parts.length - 1][0] : "";
    return (i1 + i2).toUpperCase() || "?";
  }

  var PALETTE = ["#2563eb", "#0ea5e9", "#8b5cf6", "#0d9488", "#f59e0b", "#dc2626", "#db2777", "#16a34a", "#4f46e5", "#ea580c"];
  function couleurAvatar(texte) {
    var h = 0;
    var s = String(texte || "");
    for (var i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % 997;
    return PALETTE[h % PALETTE.length];
  }

  function formatFCFA(montant) {
    return Number(montant || 0).toLocaleString("fr-FR").replace(/\u202f/g, " ") + " FCFA";
  }

  function fmtDate(iso) {
    if (!iso) return "—";
    var d = new Date(iso + (iso.length === 10 ? "T00:00:00" : ""));
    if (isNaN(d)) return iso;
    return d.toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" });
  }

  /* ---------- Badges ---------- */
  var BADGE_CLASS = {
    "Actif": "badge-success",
    "Inactif": "badge-neutral",
    "Payé": "badge-success",
    "Impayé": "badge-danger",
    "Partiellement payé": "badge-warning",
    "Présent": "badge-success",
    "Absent": "badge-danger",
    "Retard": "badge-warning",
    "Administrateur": "badge-info",
    "Professeur": "badge-neutral",
    "Surveillant": "badge-neutral",
    "Élève": "badge-info",
    "Parent": "badge-warning",
    // Statuts de rattachement (Phase 3 — membres)
    "actif": "badge-success",
    "invite": "badge-warning",
    "suspendu": "badge-danger",
    "Information": "badge-info",
    "Réunion": "badge-warning",
    "Concours": "badge-neutral",
    "Finance": "badge-danger",
    "Collège": "badge-info",
    "Lycée": "badge-warning",
    "Homme": "badge-info",
    "Femme": "badge-warning",
    "M": "badge-info",
    "F": "badge-warning",
    // Statuts de fiche de paie (valeurs serveur / libellés affichés)
    "en_attente": "badge-warning",
    "payee": "badge-success",
    "Payée": "badge-success",
    "En attente": "badge-warning"
  };

  function badgeStatut(statut) {
    var cls = BADGE_CLASS[statut] || "badge-neutral";
    return '<span class="badge ' + cls + '">' + escapeHtml(statut) + "</span>";
  }

  /* ---------- Avatar HTML ---------- */
  function avatarHTML(nomComplet, taille) {
    var cls = taille === "lg" ? "avatar avatar-lg" : taille === "sm" ? "avatar avatar-sm" : "avatar";
    return '<span class="' + cls + '" style="background:' + couleurAvatar(nomComplet) + '">' + initiales(nomComplet) + "</span>";
  }

  /* ---------- Modales ---------- */
  function openModal(id) {
    var m = document.getElementById(id);
    if (m) m.classList.add("open");
    document.body.style.overflow = "hidden";
  }
  function closeModal(id) {
    var m = document.getElementById(id);
    if (m) m.classList.remove("open");
    if (!document.querySelector(".modal-overlay.open")) document.body.style.overflow = "";
  }
  function closeAllModals() {
    document.querySelectorAll(".modal-overlay.open").forEach(function (m) { m.classList.remove("open"); });
    document.body.style.overflow = "";
  }

  // Délégation globale : [data-open], [data-close], clic sur fond, Échap
  document.addEventListener("click", function (e) {
    var opener = e.target.closest("[data-open]");
    if (opener) { openModal(opener.getAttribute("data-open")); return; }
    var closer = e.target.closest("[data-close]");
    if (closer) { closeAllModals(); return; }
    if (e.target.classList && e.target.classList.contains("modal-overlay")) closeAllModals();
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") { closeAllModals(); closeDropdowns(); }
  });

  /* ---------- Toasts ---------- */
  function toast(message, type) {
    var ico = type === "success" ? "✅" : type === "error" ? "❌" : type === "warning" ? "⚠️" : "ℹ️";
    var container = document.querySelector(".toast-container");
    if (!container) {
      container = document.createElement("div");
      container.className = "toast-container";
      document.body.appendChild(container);
    }
    var t = document.createElement("div");
    t.className = "toast " + (type || "info");
    t.innerHTML = '<span class="t-ico">' + ico + "</span><span>" + message + "</span><span class=\"t-bar\"></span>";
    container.appendChild(t);
    setTimeout(function () {
      t.classList.add("out");
      setTimeout(function () { t.remove(); }, 300);
    }, 3200);
  }

  /* ---------- Export global ---------- */
  window.SM = {
    PAGES: PAGES,
    PAGES_HORS_MENU: PAGES_HORS_MENU,
    buildLayout: buildLayout,
    getSession: getSession,
    // Capacités décidées par le serveur : à utiliser par les pages pour
    // masquer les boutons d'action (« Ajouter », « Enregistrer », …).
    capacites: capacites,
    roleCourant: roleCourant,
    porteeEleves: porteeEleves,
    peut: peut,
    monEnseignant: monEnseignant,
    titrePage: titrePage,
    pageAutorisee: pageAutorisee,
    adapterPageAuRole: adapterPageAuRole,
    escapeHtml: escapeHtml,
    initiales: initiales,
    couleurAvatar: couleurAvatar,
    formatFCFA: formatFCFA,
    fmtDate: fmtDate,
    badgeStatut: badgeStatut,
    avatarHTML: avatarHTML,
    openModal: openModal,
    closeModal: closeModal,
    closeAllModals: closeAllModals,
    toast: toast,
    animerInterface: animerInterface,
    preparerAnimations: preparerAnimations
  };

  // Lancement
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", buildLayout);
  } else {
    buildLayout();
  }
})();
