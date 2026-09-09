/* ============================================================
   SchoolManager — UI partagée
   Injection sidebar/topbar, modales, toasts, helpers
   ============================================================ */

(function () {
  "use strict";

  /* ---------- Pages du menu ---------- */
  var PAGES = [
    { key: "dashboard", lien: "dashboard.html", icone: "🏠", titre: "Tableau de bord", groupe: "Général" },
    { key: "students", lien: "students.html", icone: "👨‍🎓", titre: "Élèves", groupe: "Gestion" },
    { key: "teachers", lien: "teachers.html", icone: "👨‍🏫", titre: "Enseignants", groupe: "Gestion" },
    { key: "classes", lien: "classes.html", icone: "🏫", titre: "Classes", groupe: "Gestion" },
    { key: "subjects", lien: "subjects.html", icone: "📚", titre: "Matières", groupe: "Gestion" },
    { key: "grades", lien: "grades.html", icone: "📝", titre: "Notes", groupe: "Pédagogie" },
    { key: "report-cards", lien: "report-cards.html", icone: "📊", titre: "Bulletins", groupe: "Pédagogie" },
    { key: "timetable", lien: "timetable.html", icone: "📅", titre: "Emploi du temps", groupe: "Pédagogie" },
    { key: "mes-seances", lien: "mes-seances.html", icone: "✍️", titre: "Ma présence", groupe: "Espace enseignant", roles: ["Professeur"] },
    { key: "ma-paie", lien: "ma-paie.html", icone: "💵", titre: "Ma rémunération", groupe: "Espace enseignant", roles: ["Professeur"] },
    { key: "payments", lien: "payments.html", icone: "💰", titre: "Paiements", groupe: "Finance" },
    { key: "paie", lien: "paie.html", icone: "💶", titre: "Rémunérations", groupe: "Finance", roles: ["Administrateur"] },
    { key: "announcements", lien: "announcements.html", icone: "📢", titre: "Annonces", groupe: "Communication" },
    { key: "settings", lien: "settings.html", icone: "⚙️", titre: "Paramètres", groupe: "Système" }
  ];

  var ROLE_EMOJI = { Administrateur: "👨‍💼", Professeur: "👨‍🏫", Élève: "👨‍🎓", Parent: "👨‍👩‍👧" };

  /* ---------- Session ---------- */
  function getSession() {
    try {
      return JSON.parse(sessionStorage.getItem("sm_session") || "null");
    } catch (e) { return null; }
  }

  var TITRES = {};
  PAGES.forEach(function (p) { TITRES[p.key] = p.titre; });

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

    // Rôle courant : sert à masquer les entrées de menu réservées
    // (propriété « roles » d'une page) — les pages existantes, sans
    // restriction, restent visibles pour tous comme avant.
    var sessionRole = (function () {
      var s = getSession();
      return s ? s.role : null;
    })();

    var sidebar = document.getElementById("sidebar");
    var topbar = document.getElementById("topbar");
    if (!sidebar && !topbar) return;

    // Sidebar
    if (sidebar) {
      var nav = "";
      var lastGroupe = "";
      PAGES.forEach(function (p) {
        // Page réservée à certains rôles : masquée pour les autres.
        if (p.roles && p.roles.indexOf(sessionRole) === -1) return;
        if (p.groupe !== lastGroupe) {
          nav += '<div class="nav-section">' + p.groupe + "</div>";
          lastGroupe = p.groupe;
        }
        var act = page === p.key ? " active" : "";
        nav += '<a class="nav-link' + act + '" href="' + p.lien + '"><span class="nav-ico">' + p.icone + "</span>" + p.titre + "</a>";
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
      var sess = getSession();
      var role = sess ? sess.role : "Administrateur";
      var name = sess ? sess.nom : "Administrateur";
      var emoji = ROLE_EMOJI[role] || "👤";
      var titre = TITRES[page] || "SchoolManager";

      var notifs = SD.annonces.slice(0, 3).map(function (a) {
        return '<button class="dropdown-item" data-go="announcements"><span>📢</span>' + escapeHtml(a.titre) + "</button>";
      }).join("");

      topbar.innerHTML =
        '<div class="topbar-left">' +
        '  <button class="btn-icon menu-btn" id="btnMenu" title="Menu">☰</button>' +
        '  <h1 class="page-title">' + titre + "</h1>" +
        "</div>" +
        '<div class="topbar-right">' +
        (chipMode() ? '  <span class="demo-chip">' + chipMode() + "</span>" : "") +
        '  <div class="dropdown">' +
        '    <button class="btn-icon" id="btnNotif" title="Notifications">🔔<span class="notif-dot"></span></button>' +
        '    <div class="dropdown-menu" id="menuNotif">' +
        '      <div class="dropdown-head">Notifications</div>' +
        notifs +
        '      <div class="dropdown-sep"></div>' +
        '      <button class="dropdown-item" data-go="announcements"><span>🔔</span>Toutes les annonces</button>' +
        "    </div>" +
        "  </div>" +
        '  <div class="dropdown">' +
        '    <button class="user-chip" id="btnUser" title="Mon compte">' +
        '      <span class="avatar" style="background:' + couleurAvatar(name) + '">' + initiales(name) + "</span>" +
        '      <span class="u-info"><span class="u-name" style="display:block">' + escapeHtml(name) + '</span><span class="u-role">' + escapeHtml(role) + "</span></span>" +
        "    </button>" +
        '    <div class="dropdown-menu" id="menuUser" style="right:0">' +
        '      <div class="dropdown-head">' + emoji + " Compte</div>" +
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
    "Élève": "badge-info",
    "Parent": "badge-warning",
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
    t.innerHTML = '<span class="t-ico">' + ico + "</span><span>" + message + "</span>";
    container.appendChild(t);
    setTimeout(function () {
      t.classList.add("out");
      setTimeout(function () { t.remove(); }, 300);
    }, 3200);
  }

  /* ---------- Export global ---------- */
  window.SM = {
    PAGES: PAGES,
    buildLayout: buildLayout,
    getSession: getSession,
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
    toast: toast
  };

  // Lancement
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", buildLayout);
  } else {
    buildLayout();
  }
})();
