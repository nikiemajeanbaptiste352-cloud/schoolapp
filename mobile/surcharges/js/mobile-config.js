/* ============================================================
   SchoolManager — Configuration de la version MOBILE
   ------------------------------------------------------------
   Ce fichier n'existe QUE dans mobile/ : il est ajouté par
   outils/assembler-www.js pendant la fabrication de l'application.
   Le site web publié sur Vercel n'est pas touché.

   Il est chargé AVANT js/api.js sur les 18 pages et fait trois choses :

     1. il fixe l'adresse du backend — dans l'application, la page est
        servie en local (https://localhost) et le calcul automatique de
        js/api.js viserait 127.0.0.1:8000, un serveur qui n'existe pas
        sur le téléphone ;

     2. il rend la session persistante — le site utilise sessionStorage,
        effacé à la fermeture : sans cela, l'utilisateur devrait se
        reconnecter à chaque ouverture de l'application ;

     3. il masque l'écran de démarrage natif quand la page est prête.

   Sur le site web, ce fichier n'est jamais chargé : le comportement
   d'origine est strictement inchangé.
   ============================================================ */

(function () {
  "use strict";

  /* ---------- 1. Adresse du backend de production ---------- */
  var API_PRODUCTION = "https://schoolapp-flame-six.vercel.app/api/v1";
  window.SM_API_BASE = API_PRODUCTION;
  window.SM_MOBILE = true;

  /* ---------- 2. Session persistante ----------
     Le site écrit la session dans sessionStorage (sm_token, sm_user,
     sm_session). Ces clés disparaissent à la fermeture de l'application.
     On fait donc pointer sessionStorage vers localStorage, qui lui est
     conservé. Toutes les pages continuent d'utiliser « sessionStorage » :
     aucune ligne du site n'a besoin d'être modifiée.
     Si le navigateur refuse l'opération, on continue sans persistance
     (dégradation sans casse : l'application reste utilisable). */
  try {
    Object.defineProperty(window, "sessionStorage", {
      configurable: true,
      get: function () {
        return window.localStorage;
      }
    });
  } catch (e) {
    /* stockage d'origine conservé */
  }

  /* ---------- 3. Écran de démarrage natif ---------- */
  function masquerDemarrage() {
    try {
      var C = window.Capacitor;
      if (C && C.Plugins && C.Plugins.SplashScreen) {
        C.Plugins.SplashScreen.hide();
      }
    } catch (e) {
      /* pas d'écran natif (navigateur) : rien à faire */
    }
  }
  window.SM_MASQUER_DEMARRAGE = masquerDemarrage;

  /* Sécurité : on ne reste jamais bloqué sur l'écran de démarrage. */
  window.setTimeout(masquerDemarrage, 20000);

  /* Page de connexion : masquage dès que la page est affichée.
     Les pages de l'application, elles, appellent le masquage après le
     chargement des données (voir js/live.js). */
  var chemin = window.location.pathname || "";
  if (/\/$/.test(chemin) || /\/index\.html$/.test(chemin)) {
    window.addEventListener("load", function () {
      window.setTimeout(masquerDemarrage, 250);
    });
  }
})();
