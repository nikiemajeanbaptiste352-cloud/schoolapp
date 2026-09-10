/* SchoolManager — V2 « Aurore »
   Animations de la page d'accueil (index.html).

   Les pages de l'application chargent js/ui.js, qui gère déjà apparitions,
   compteurs et ondes : ce fichier ne fait donc rien s'il détecte js/ui.js
   (window.SM) afin d'éviter tout doublon.

   ES5 uniquement, aucune dépendance, aucun build. */
(function () {
  "use strict";

  if (window.SM) return; // interface de l'application : déjà animée par ui.js

  var MOUVEMENT_REDUIT = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);

  var SEL_APPARITION =
    ".lp-chip, .lp-hero h1, .lp-lead, .lp-points, .lp-cta, .lp-visuel, .lp-kente, " +
    ".lp-conf-item, .lp-sec-titre, .lp-carte, .lp-role, .lp-etape, .lp-atouts li, " +
    ".lp-faq-item, .lp-cta-band-in, .lp-auth-head, .login-card";

  var obs = null;

  function estVisible(el) {
    return !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  }

  function creerObservateur() {
    if (obs) return obs;
    if (!("IntersectionObserver" in window)) return null;
    obs = new window.IntersectionObserver(function (entrees) {
      for (var i = 0; i < entrees.length; i++) {
        var el = entrees[i].target;
        obs.unobserve(el);
        el.classList.add("sm-in");
      }
    }, { threshold: 0, rootMargin: "0px 0px -6% 0px" });
    return obs;
  }

  function reveler(el) {
    el.classList.add("sm-in");
  }

  function preparerApparitions() {
    var o = creerObservateur();
    if (!o) return;
    var h = window.innerHeight || document.documentElement.clientHeight || 800;
    var liste = document.querySelectorAll(SEL_APPARITION);
    var n = 0;
    for (var i = 0; i < liste.length; i++) {
      var el = liste[i];
      if (el.getAttribute("data-sm-rv") || !estVisible(el)) continue;
      var r = el.getBoundingClientRect();
      var deja = r.top < h * 0.94 && r.bottom > 0;
      el.setAttribute("data-sm-rv", "1");
      el.classList.add("sm-rv");
      el.style.setProperty("--sm-d", deja ? "0ms" : Math.min(n, 8) * 60 + "ms");
      n++;
      if (deja) revelerDiffere(el, Math.min(n, 8) * 60);
      else o.observe(el);
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

  // Filet de sécurité : si l'observateur ne s'est jamais déclenché, on révèle tout.
  function securiteApparitions() {
    if (document.querySelector(".sm-rv.sm-in")) return;
    var liste = document.querySelectorAll(".sm-rv:not(.sm-in)");
    for (var i = 0; i < liste.length; i++) liste[i].classList.add("sm-in");
  }

  /* Onde au clic sur les boutons de la page d'accueil */
  function ondeClic(e) {
    var b = e.target && e.target.closest ? e.target.closest(".lp-btn, .lp-nav-cta, .btn-google, .lp-mode-btn") : null;
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

  /* Barre de progression lors d'une vraie navigation (hors ancres) */
  function barreCharge() {
    var b = document.getElementById("smCharge");
    if (!b) {
      b = document.createElement("div");
      b.id = "smCharge";
      document.body.appendChild(b);
    }
    b.classList.remove("sm-charge-on");
    void b.offsetWidth;
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

  /* ---------- Menu de navigation mobile ----------
     Indépendant des animations : la navigation doit rester utilisable
     même si l'utilisateur a demandé moins de mouvements. */
  function initNavigation() {
    var burger = document.getElementById("lpBurger");
    var panneau = document.getElementById("lpNavLinks");
    if (!burger || !panneau) return;

    function estMobile() {
      return !!(window.matchMedia && window.matchMedia("(max-width: 1020px)").matches);
    }

    function fermer() {
      panneau.classList.remove("is-ouvert");
      burger.setAttribute("aria-expanded", "false");
      burger.setAttribute("aria-label", "Ouvrir le menu");
    }

    burger.addEventListener("click", function (e) {
      e.stopPropagation();
      if (!estMobile()) return;
      var ouvert = panneau.classList.toggle("is-ouvert");
      burger.setAttribute("aria-expanded", ouvert ? "true" : "false");
      burger.setAttribute("aria-label", ouvert ? "Fermer le menu" : "Ouvrir le menu");
    });

    // Un clic sur un lien du menu referme le panneau.
    panneau.addEventListener("click", function (e) {
      if (e.target && e.target.closest && e.target.closest("a")) fermer();
    });

    document.addEventListener("click", function (e) {
      if (!panneau.classList.contains("is-ouvert")) return;
      if (e.target === burger || burger.contains(e.target)) return;
      if (panneau.contains(e.target)) return;
      fermer();
    });

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") fermer();
    });

    // Retour à la disposition bureau : on referme le panneau.
    window.addEventListener("resize", function () {
      if (!estMobile()) fermer();
    });

    // Lien de la section en cours mis en évidence pendant le défilement.
    var liens = panneau.querySelectorAll('a[href^="#"]');
    var cibles = [];
    for (var i = 0; i < liens.length; i++) {
      var id = (liens[i].getAttribute("href") || "").slice(1);
      var cible = id ? document.getElementById(id) : null;
      if (cible) cibles.push({ lien: liens[i], cible: cible });
    }
    if (cibles.length && "IntersectionObserver" in window) {
      var courant = null;
      var obs2 = new window.IntersectionObserver(function (entrees) {
        for (var j = 0; j < entrees.length; j++) {
          if (!entrees[j].isIntersecting) continue;
          for (var k = 0; k < cibles.length; k++) {
            if (cibles[k].cible !== entrees[j].target) continue;
            if (courant) courant.removeAttribute("aria-current");
            courant = cibles[k].lien;
            courant.setAttribute("aria-current", "true");
            break;
          }
          break;
        }
      }, { rootMargin: "-45% 0px -50% 0px" });
      for (var m = 0; m < cibles.length; m++) obs2.observe(cibles[m].cible);
    }
  }

  function lancer() {
    initNavigation();
    if (MOUVEMENT_REDUIT) return;
    preparerApparitions();
    // Le contenu (vues de connexion, invitation) se remplit après coup.
    setTimeout(preparerApparitions, 600);
    setTimeout(preparerApparitions, 1500);
    setTimeout(securiteApparitions, 3000);
    document.addEventListener("click", ondeClic);
    document.addEventListener("click", lienCharge);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", lancer);
  } else {
    lancer();
  }
})();
