/* ============================================================
   SchoolManager — Bootstrap « données du serveur »
   ------------------------------------------------------------
   Chargé sur chaque page (pages/*.html), APRÈS js/data.js et
   AVANT js/ui.js / <page>.js.

   L'application ne contient plus AUCUNE donnée fictive : elle
   fonctionne exclusivement avec le backend FastAPI.

   - Page ouverte en fichier local (file://) → écran d'aide.
   - Page protégée sans session valide → retour à la connexion.
   - Sinon : GET /api/v1/etat (requête synchrone, compatible
     ES5), reconstruction de window.SD via window.construireSD,
     puis lancement de ui.js + script de la page
     (window.SM_MODE = "api").
   ============================================================ */

(function () {
  "use strict";

  // Base de l'API : réutilise celle de js/api.js (relative au backend, ou
  // http://127.0.0.1:8000/api/v1 quand le front est servi séparément).
  var BASE = (window.API && window.API.base) || "/api/v1";

  /* ---------- Chargement séquentiel de scripts (ui.js puis page) ---------- */
  function chargerScripts(sources) {
    var i = 0;
    function suivant() {
      if (i >= sources.length) return;
      var s = document.createElement("script");
      s.src = sources[i];
      s.onload = suivant;
      s.onerror = suivant; // on continue même si un script échoue
      document.body.appendChild(s);
      i++;
    }
    suivant();
  }

  /* ---------- Lecture du jeton (mêmes clés que js/api.js) ---------- */
  function obtenirJeton() {
    try {
      return sessionStorage.getItem("sm_token") || null;
    } catch (e) { return null; }
  }

  function effacerJeton() {
    try {
      sessionStorage.removeItem("sm_token");
      sessionStorage.removeItem("sm_user");
    } catch (e) { /* stockage indisponible */ }
  }

  /* ---------- Normalisation /etat → jeu de données SD ---------- */
  function sansId(obj) {
    if (!obj) return null;
    var copie = {};
    Object.keys(obj).forEach(function (k) {
      if (k !== "id") copie[k] = obj[k];
    });
    return copie;
  }

  function mapperEtat(etat) {
    var ecole = etat.ecole;
    if (ecole && typeof ecole === "object") {
      ecole = sansId(ecole);
    } else {
      // Base vide : l'école n'est pas encore configurée → objet minimal
      // neutre pour que les pages s'affichent sans erreur.
      ecole = {
        nom: "", sigle: "", slogan: "", annee: "",
        devise: "FCFA", telephone: "", email: "", adresse: "", version: "1.0.0"
      };
    }

    var classes = (etat.classes || []).map(function (c) {
      return { id: c.id, nom: c.nom, cycle: c.cycle, salle: c.salle, principal: c.principal };
    });

    var matieres = etat.matieres || [];

    var enseignants = (etat.enseignants || []).map(function (e) {
      return {
        id: e.id,
        nom: e.nom,
        prenom: e.prenom,
        sexe: e.sexe,
        tel: e.tel,
        email: e.email,
        matiere: e.matiere,
        classes: e.classes || [],
        statut: e.statut
      };
    });

    var eleves = (etat.eleves || []).map(function (e) {
      return {
        id: e.id,
        nom: e.nom,
        prenom: e.prenom,
        sexe: e.sexe,
        naissance: e.naissance,
        classe: e.classe,
        statut: e.statut,
        inscription: e.inscription,
        parent: sansId(e.parent)
      };
    });

    // Notes : forme front { id, eleveId, classeId, matiereId, eval, note }
    var notes = (etat.notes || []).map(function (n) {
      return {
        id: String(n.id),
        eleveId: n.eleveId,
        classeId: n.classeId,
        matiereId: n.matiereId,
        eval: n.eval,
        note: n.note
      };
    });

    // Présences : forme front { eleveId, date, statut, libelle }
    var presences = (etat.presences || []).map(function (p) {
      return { eleveId: p.eleveId, date: p.date, statut: p.statut, libelle: p.libelle };
    });

    // Paiements : forme front { eleveId, motif, total, paiements: [...] }
    var paiements = (etat.paiements || []).map(function (p) {
      var versements = (p.versements || []).map(function (v) {
        return { montant: v.montant, date: v.date, mode: v.mode };
      });
      return { eleveId: p.eleveId, motif: p.motif, total: p.total, paiements: versements };
    });

    var annonces = etat.annonces || [];

    return {
      ecole: ecole,
      classes: classes,
      matieres: matieres,
      enseignants: enseignants,
      eleves: eleves,
      notes: notes,
      presences: presences,
      paiements: paiements,
      annonces: annonces
    };
  }

  /* ---------- Appel synchrone GET /api/v1/etat ---------- */
  function chargerEtat() {
    try {
      var xhr = new XMLHttpRequest();
      xhr.open("GET", BASE + "/etat", false); // synchrone : window.SD prêt avant ui/page
      xhr.setRequestHeader("Accept", "application/json");
      var jeton = obtenirJeton();
      if (jeton) xhr.setRequestHeader("Authorization", "Bearer " + jeton);
      xhr.send(null);
      if (xhr.status === 200) {
        return JSON.parse(xhr.responseText || "{}");
      }
      if (xhr.status === 401) {
        // Jeton invalide ou expiré → retour à l'écran de connexion
        effacerJeton();
        window.location.replace("../index.html");
        return null;
      }
      return null;
    } catch (e) {
      return null; // réseau injoignable → écran « serveur indisponible »
    }
  }

  /* ---------- Démarrage ---------- */
  var currentScript = document.currentScript || (function () {
    var ss = document.getElementsByTagName("script");
    return ss[ss.length - 1];
  })();
  var pageJs = currentScript ? currentScript.getAttribute("data-page-js") : null;

  /* ---------- Écran « serveur indisponible » (plus jamais de données fictives) ---------- */
  function afficherIndisponible(titre, message) {
    var masque = document.createElement("div");
    masque.style.cssText =
      "position:fixed;inset:0;z-index:9999;background:#f4f6fb;display:flex;align-items:center;justify-content:center;padding:24px;font-family:system-ui,-apple-system,'Segoe UI',sans-serif";
    var carte = document.createElement("div");
    carte.style.cssText =
      "max-width:520px;background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:28px;text-align:center;box-shadow:0 10px 30px rgba(15,23,42,.08)";
    carte.innerHTML =
      '<div style="font-size:44px">🔌</div>' +
      "<h2 style='margin:12px 0 8px;font-size:20px;color:#0f172a'>" + titre + "</h2>" +
      "<p style='margin:0 0 20px;color:#475569;font-size:14px;line-height:1.6'>" + message + "</p>" +
      '<button type="button" style="background:#2563eb;color:#fff;border:0;border-radius:8px;padding:10px 22px;font-size:14px;cursor:pointer">Recharger</button>';
    carte.querySelector("button").addEventListener("click", function () { window.location.reload(); });
    masque.appendChild(carte);
    document.body.appendChild(masque);
  }

  /* ---------- Démarrage — mode API uniquement ---------- */
  var enLigne = !!(window.API && window.API.enLigne && window.API.enLigne());
  var jeton = obtenirJeton();

  // Page protégée sans session valide → page de connexion
  if (document.body.dataset.auth === "true" && !jeton) {
    window.location.replace("../index.html");
    return;
  }

  // Page ouverte en fichier local (file://) : aucun serveur possible
  if (!enLigne) {
    afficherIndisponible(
      "Application ouverte en fichier local",
      "Les données fictives de démonstration ont été supprimées.<br>" +
        "Démarrez le serveur SchoolManager puis ouvrez : <b>http://127.0.0.1:8000</b>"
    );
    return;
  }

  var etat = chargerEtat(); // synchrone
  if (!etat) {
    if (!obtenirJeton()) return; // 401 : la redirection vers la connexion est déjà lancée
    afficherIndisponible(
      "Serveur injoignable",
      "Vérifiez que le backend SchoolManager est démarré sur <b>http://127.0.0.1:8000</b>, puis rechargez la page."
    );
    return;
  }

  try {
    window.SD = window.construireSD(mapperEtat(etat));
  } catch (e) {
    console.error("Live : reconstruction de window.SD impossible.", e);
    afficherIndisponible(
      "Données illisibles",
      "L'état renvoyé par le serveur est invalide : " + (e && e.message ? e.message : e)
    );
    return;
  }
  window.SM_MODE = "api";

  /* ---------- Rafraîchissement après écriture API ---------- */
  // Les scripts de page capturent des références vers les tableaux de
  // window.SD (ex. var eleves = SD.eleves) et les fonctions de calcul de
  // data.js referment ces mêmes tableaux : on mute donc les tableaux EXISTANTS
  // en place (sans reconstruire window.SD), puis on met à jour l'objet école.
  function remplacerEnPlace(tableau, nouvelles) {
    var liste = nouvelles || [];
    tableau.splice.apply(tableau, [0, tableau.length].concat(liste));
  }
  window.rafraichirEtat = function () {
    if (!window.API || !window.API.etat) {
      return Promise.reject({ reseau: false, detail: "API indisponible." });
    }
    return window.API.etat().then(function (etat) {
      var d = mapperEtat(etat);
      var sd = window.SD;
      if (!sd) {
        window.SD = window.construireSD(d);
        return window.SD;
      }
      remplacerEnPlace(sd.classes, d.classes);
      remplacerEnPlace(sd.matieres, d.matieres);
      remplacerEnPlace(sd.enseignants, d.enseignants);
      remplacerEnPlace(sd.eleves, d.eleves);
      remplacerEnPlace(sd.notes, d.notes);
      remplacerEnPlace(sd.presences, d.presences);
      remplacerEnPlace(sd.paiements, d.paiements);
      remplacerEnPlace(sd.annonces, d.annonces);
      var nouvelleEcole = d.ecole || {};
      var cles = Object.keys(nouvelleEcole);
      Object.keys(sd.ecole || {}).forEach(function (k) {
        if (cles.indexOf(k) === -1) delete sd.ecole[k];
      });
      cles.forEach(function (k) { sd.ecole[k] = nouvelleEcole[k]; });
      return sd;
    });
  };

  // Lance ui.js puis le script de la page (aucun inline ne les suit)
  var scripts = ["../js/ui.js"];
  if (pageJs) scripts.push("../js/" + pageJs);
  chargerScripts(scripts);
})();
