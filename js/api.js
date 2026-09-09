/* ============================================================
   SchoolManager — Client API (backend FastAPI)
   ------------------------------------------------------------
   Adaptateur fetch vers /api/v1 avec jeton JWT (Bearer).

   - Connexion réelle : API.connexion(email, motDePasse)
     -> POST /api/v1/auth/login, mémorise le jeton (sm_token)
        et le profil (sm_user), renvoie { access_token, user, ecole, annee }.
   - Session : la page de connexion écrit aussi sm_session
     { role, email, nom } pour l'interface existante (SM.getSession).
   - Si l'application est ouverte en file:// (protocole local) ou que le
     serveur est injoignable, chaque appel échoue avec { reseau: true } :
     l'interface affiche alors un écran « démarrez le serveur » (aucune
     donnée fictive n'existe plus).
   - Les méthodes GET exposées correspondent 1:1 aux routes du backend
     (voir backend/app/routers/*.py).
   ============================================================ */

(function () {
  "use strict";

  // URL de base de l'API. Normalement relative (/api/v1) : le backend sert
  // aussi le front. Si la page est servie par un AUTRE serveur (Live Server,
  // python -m http.server…), on cible le backend SchoolManager local.
  // Surcharge possible : <script>window.SM_API_BASE="…";</script> avant api.js.
  function baseApi() {
    if (typeof window !== "undefined" && window.SM_API_BASE) return window.SM_API_BASE;
    try {
      if (!window.location || !/^https?:$/.test(window.location.protocol)) {
        return "/api/v1"; // file:// → jamais utilisé (mode démo)
      }
      var port = window.location.port || (window.location.protocol === "https:" ? "443" : "80");
      var hote = window.location.hostname || "";
      // Page servie par un AUTRE serveur local (Live Server, python -m
      // http.server…) → on cible le backend SchoolManager en 127.0.0.1:8000.
      // Cas particulier du dev local uniquement : si le site est servi sur un
      // hôte distant (ex. Vercel), on reste en même origine (/api/v1) car le
      // backend est déployé avec le front sur le même domaine.
      var hoteLocal = hote === "localhost" || hote === "127.0.0.1" || hote === "::1";
      if (hoteLocal && port !== "8000") {
        return "http://127.0.0.1:8000/api/v1";
      }
    } catch (e) { /* on garde le chemin relatif */ }
    return "/api/v1";
  }
  var BASE = baseApi();

  var CLE_JETON = "sm_token";
  var CLE_USER = "sm_user";
  var DELAI_MS = 4000;

  // L'API n'est joignable que si la page est servie en http(s) par le backend.
  var EN_LIGNE =
    typeof window !== "undefined" &&
    window.location &&
    /^https?:$/.test(window.location.protocol);

  /* ---------- Jeton / profil ---------- */
  function obtenirJeton() {
    try { return sessionStorage.getItem(CLE_JETON) || null; }
    catch (e) { return null; }
  }
  function memoriserJeton(t) {
    try {
      if (t) sessionStorage.setItem(CLE_JETON, t);
      else sessionStorage.removeItem(CLE_JETON);
    } catch (e) { /* stockage indisponible */ }
  }
  function effacerJeton() { memoriserJeton(null); }
  function aUnJeton() { return !!obtenirJeton(); }

  function memoriserUtilisateur(u) {
    try {
      if (u) sessionStorage.setItem(CLE_USER, JSON.stringify(u));
      else sessionStorage.removeItem(CLE_USER);
    } catch (e) { /* stockage indisponible */ }
  }
  function utilisateur() {
    try { return JSON.parse(sessionStorage.getItem(CLE_USER) || "null"); }
    catch (e) { return null; }
  }

  /* ---------- Requête générique ---------- */
  // Rejette un objet { reseau, statut, detail } :
  //   reseau = true  -> serveur injoignable (mode démo / hors-ligne)
  //   reseau = false -> réponse HTTP en erreur (detail = message serveur)
  function requete(methode, chemin, corps, opts) {
    opts = opts || {};
    var avecJeton = opts.jeton !== false;

    return new Promise(function (resoudre, rejeter) {
      if (!EN_LIGNE) {
        rejeter({ reseau: true, statut: 0, detail: "Application ouverte sans serveur accessible." });
        return;
      }

      var init = {
        method: methode,
        headers: { Accept: "application/json" },
        cache: "no-store"
      };
      if (corps !== undefined && corps !== null) {
        init.headers["Content-Type"] = "application/json";
        init.body = JSON.stringify(corps);
      }
      var tok = avecJeton ? obtenirJeton() : null;
      if (tok) init.headers.Authorization = "Bearer " + tok;

      var chrono = setTimeout(function () {
        rejeter({ reseau: true, statut: 0, detail: "Le serveur ne répond pas (délai dépassé)." });
      }, DELAI_MS);

      var p;
      try { p = fetch(BASE + chemin, init); }
      catch (e) {
        clearTimeout(chrono);
        rejeter({ reseau: true, statut: 0, detail: "Réseau indisponible." });
        return;
      }

      p.then(function (rep) {
        clearTimeout(chrono);
        var ctype = rep.headers.get("content-type") || "";
        var parse = ctype.indexOf("application/json") !== -1 ? rep.json() : Promise.resolve(null);

        parse.then(function (data) {
          if (rep.ok) { resoudre(data); return; }
          var detail = (data && (data.detail !== undefined ? data.detail : data.message)) || ("Erreur " + rep.status);
          if (typeof detail !== "string") {
            try { detail = JSON.stringify(detail); } catch (e2) { detail = "Erreur " + rep.status; }
          }
          if (rep.status === 401 && tok) effacerJeton(); // jeton expiré/invalide
          rejeter({ reseau: false, statut: rep.status, detail: detail });
        }).catch(function () {
          rejeter({ reseau: false, statut: rep.status, detail: "Erreur " + rep.status });
        });
      }).catch(function () {
        clearTimeout(chrono);
        rejeter({ reseau: true, statut: 0, detail: "Impossible de joindre le serveur." });
      });
    });
  }

  function get(chemin, opts) { return requete("GET", chemin, undefined, opts); }
  function post(chemin, corps, opts) { return requete("POST", chemin, corps, opts); }
  function put(chemin, corps, opts) { return requete("PUT", chemin, corps, opts); }
  function del(chemin, opts) { return requete("DELETE", chemin, undefined, opts); }

  function enc(v) { return encodeURIComponent(v); }

  function params(obj) {
    var parts = [];
    Object.keys(obj || {}).forEach(function (k) {
      var v = obj[k];
      if (v !== undefined && v !== null && String(v) !== "") {
        parts.push(enc(k) + "=" + enc(v));
      }
    });
    return parts.length ? "?" + parts.join("&") : "";
  }

  /* ---------- API publique ---------- */
  var API = {
    /* --- Réseau / session --- */
    enLigne: function () { return EN_LIGNE; },
    aUnJeton: aUnJeton,
    jeton: obtenirJeton,
    utilisateur: utilisateur,

    // Teste rapidement la disponibilité du backend (GET /health).
    disponible: function () {
      if (!EN_LIGNE) return Promise.resolve(false);
      return get("/health", { jeton: false })
        .then(function () { return true; })
        .catch(function () { return false; });
    },

    connexion: function (email, motDePasse) {
      return post("/auth/login", { email: email, password: motDePasse }, { jeton: false })
        .then(function (data) {
          if (data && data.access_token) {
            memoriserJeton(data.access_token);
            memoriserUtilisateur(data.user || null);
          }
          return data;
        });
    },

    // Inscription publique (compte Parent uniquement) : POST /auth/inscription.
    // Renvoie un jeton comme la connexion → l'utilisateur est connecté aussitôt.
    inscription: function (nom, email, motDePasse) {
      return post("/auth/inscription", { nom: nom, email: email, password: motDePasse }, { jeton: false })
        .then(function (data) {
          if (data && data.access_token) {
            memoriserJeton(data.access_token);
            memoriserUtilisateur(data.user || null);
          }
          return data;
        });
    },

    /* --- Connexion par code email (sans mot de passe) --- */
    // Méthodes de connexion actives (google / code_email) : GET /auth/options.
    optionsAuth: function () {
      return get("/auth/options", { jeton: false });
    },
    // Demande l'envoi d'un code à 6 chiffres : POST /auth/code/demander.
    demanderCode: function (email, nom) {
      return post("/auth/code/demander", { email: email, nom: nom || null }, { jeton: false });
    },
    // Valide le code reçu et connecte (crée un compte Parent si besoin).
    validerCode: function (email, code, nom) {
      return post("/auth/code/valider", { email: email, code: code, nom: nom || null }, { jeton: false })
        .then(function (data) {
          if (data && data.access_token) {
            memoriserJeton(data.access_token);
            memoriserUtilisateur(data.user || null);
          }
          return data;
        });
    },

    /* --- Connexion Google (OAuth) --- */
    // URL de démarrage (redirection plein écran vers Google puis retour).
    urlConnexionGoogle: function () {
      return BASE + "/auth/google";
    },

    // Gestion des comptes (administrateur uniquement).
    comptes: function () { return get("/auth/comptes"); },
    creerCompte: function (corps) { return post("/auth/comptes", corps); },

    deconnexion: function () {
      effacerJeton();
      memoriserUtilisateur(null);
    },

    profil: function () { return get("/auth/me"); },

    /* --- Référentiel --- */
    ecole: function () { return get("/ecole"); },
    // Crée la fiche école (POST /ecole) : base vide non encore configurée.
    creerEcole: function (corps) { return post("/ecole", corps); },
    majEcole: function (corps) { return put("/ecole", corps); },

    annonces: function () { return get("/annonces"); },
    creerAnnonce: function (corps) { return post("/annonces", corps); },
    majAnnonce: function (id, corps) { return put("/annonces/" + enc(id), corps); },
    supprimerAnnonce: function (id) { return del("/annonces/" + enc(id)); },

    classes: function () { return get("/classes"); },
    classe: function (id) { return get("/classes/" + enc(id)); },
    creerClasse: function (corps) { return post("/classes", corps); },
    majClasse: function (id, corps) { return put("/classes/" + enc(id), corps); },
    supprimerClasse: function (id) { return del("/classes/" + enc(id)); },
    emploiDuTemps: function (classeId) { return get("/classes/" + enc(classeId) + "/emploi-du-temps"); },

    matieres: function () { return get("/matieres"); },
    creerMatiere: function (corps) { return post("/matieres", corps); },
    majMatiere: function (id, corps) { return put("/matieres/" + enc(id), corps); },
    supprimerMatiere: function (id) { return del("/matieres/" + enc(id)); },

    enseignants: function () { return get("/enseignants"); },
    enseignant: function (id) { return get("/enseignants/" + enc(id)); },
    creerEnseignant: function (corps) { return post("/enseignants", corps); },
    majEnseignant: function (id, corps) { return put("/enseignants/" + enc(id), corps); },
    supprimerEnseignant: function (id) { return del("/enseignants/" + enc(id)); },

    /* --- Élèves --- */
    eleves: function (filtres) { return get("/eleves/" + params(filtres)); },
    ficheEleve: function (eleveId) { return get("/eleves/" + enc(eleveId)); },
    creerEleve: function (corps) { return post("/eleves/", corps); },
    majEleve: function (eleveId, corps) { return put("/eleves/" + enc(eleveId), corps); },
    supprimerEleve: function (eleveId) { return del("/eleves/" + enc(eleveId)); },

    /* --- Pédagogie --- */
    notes: function (filtres) { return get("/notes" + params(filtres)); },
    enregistrerNotes: function (corps) { return put("/notes", corps); },
    // Supprime une note précise (élève + matière + évaluation) : case vidée
    // à l'écran de saisie puis « Enregistrer ».
    supprimerNote: function (eleveId, matiereId, evalNom) {
      return del("/notes" + params({ eleveId: eleveId, matiereId: matiereId, eval: evalNom }));
    },
    statsNotes: function (filtres) { return get("/notes/stats" + params(filtres)); },
    bulletins: function (classeId) { return get("/classes/" + enc(classeId) + "/bulletins"); },

    /* --- Présences & paiements --- */
    presencesEleve: function (eleveId) { return get("/eleves/" + enc(eleveId) + "/presences"); },
    pointerPresence: function (corps) { return post("/presences", corps); },
    paiements: function (filtres) { return get("/paiements" + params(filtres)); },
    statsPaiements: function () { return get("/paiements/stats"); },
    // Encaisser un versement. Si l'élève n'a pas encore de dossier côté
    // serveur, un dossier par défaut est créé (motif/total facultatifs).
    versement: function (eleveId, corps) { return post("/paiements/" + enc(eleveId) + "/versements", corps); },

    /* --- Tableau de bord --- */
    tableauDeBord: function () { return get("/dashboard"); },

    /* --- État complet (bootstrap du front) --- */
    // Récupère l'instantané complet /api/v1/etat. Utilisé par le
    // chargeur synchrone de js/live.js (qui reconstruit window.SD).
    etat: function () { return get("/etat"); },

    // Base de l'API effective (exportée pour js/live.js).
    base: BASE
  };

  window.API = API;
  window.SMAPI = API; // alias
})();
