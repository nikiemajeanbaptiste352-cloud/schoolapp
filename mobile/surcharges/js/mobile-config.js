/* ============================================================
   SchoolManager — Configuration de la version MOBILE
   ------------------------------------------------------------
   Ce fichier n'existe QUE dans mobile/ : il est ajouté par
   outils/assembler-www.js pendant la fabrication de l'application.
   Le site web publié sur Vercel n'est pas touché.

   Il est chargé AVANT js/api.js sur les 18 pages et fait quatre choses :

     1. il fixe l'adresse du backend — dans l'application, la page est
        servie en local (https://localhost) et le calcul automatique de
        js/api.js viserait 127.0.0.1:8000, un serveur qui n'existe pas
        sur le téléphone ;

     2. il rend la session persistante — le site utilise sessionStorage,
        effacé à la fermeture : sans cela, l'utilisateur devrait se
        reconnecter à chaque ouverture de l'application ;

     3. il masque l'écran de démarrage natif quand la page est prête ;

     4. il plaque la « coque d'application » : le document ne défile plus,
        seule la zone de contenu défile. Sans cela, les écrans se
        comportaient comme des pages web (la page entière glissait sous la
        barre du haut). Sur la page publique du site, il se contente de
        porter les champs de saisie à 16 px, pour que le téléphone ne zoome
        pas dès qu'on les touche.

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

  /* ---------- 4. Coque d'application : écrans fixes ----------
     Sur le site web, chaque écran est un document qui défile : la barre du
     haut et le contenu glissent ensemble, comme sur un site. Dans une
     application, le cadre ne bouge pas — seules les données défilent.

     On plaque donc une coque sur les pages qui portent la mise en page de
     l'application (`.app`, c'est-à-dire les 16 pages de `pages/`) :

        html/body ....... hauteur de l'écran, débordement masqué
        .content ........ seul bloc défilable, avec arrêt du rebond

     La règle n'est posée que si `.app` existe : le site public
     (`site.html`) et la page de connexion gardent exactement leur
     comportement d'origine. Le site publié sur Vercel n'est pas concerné,
     ce fichier n'y étant jamais chargé. */
  var COQUE_CSS = [
    "@media screen{",
    "html.sm-app-shell,html.sm-app-shell body{height:100%;overflow:hidden;overscroll-behavior:none}",
    "html.sm-app-shell body{min-height:0}",
    "html.sm-app-shell .app{height:100%;min-height:0}",
    "html.sm-app-shell .main{height:100%;min-height:0}",
    "html.sm-app-shell .sidebar{height:100%}",
    "html.sm-app-shell .topbar{flex:0 0 auto}",
    /* Barre d'etat du telephone (heure, batterie...). Le systeme peut laisser
       la page se dessiner dessous, notamment sur Android 15 et suivants ou
       l'affichage « bord a bord » est impose : sans precaution, le titre de
       l'ecran passe sous l'heure du telephone. On reserve donc la hauteur
       annoncee par le systeme. Si elle vaut 0 (page deja cadree), rien ne
       change. Le retrait est applique au bandeau lui-meme et non a son
       contenu, pour que le fond bleu continue de remplir la zone. */
    "html.sm-app-shell .topbar{padding-top:env(safe-area-inset-top,0px);",
    "height:calc(var(--topbar-h,64px) + env(safe-area-inset-top,0px))}",
    "html.sm-app-shell .sidebar{padding-top:env(safe-area-inset-top,0px)}",
    "html.sm-app-shell .content{flex:1 1 auto;min-height:0;overflow-y:auto;",
    "-webkit-overflow-scrolling:touch;overscroll-behavior:contain;",
    "padding-bottom:calc(env(safe-area-inset-bottom,0px) + 40px)}",
    "}",
    /* Barre de navigation du telephone (js/ui.js) : elle est fixe au bas de
       l'ecran, donc il faut lui reserver de la place, sinon la derniere
       ligne d'un tableau ou un bouton resterait cache dessous. */
    "@media screen and (max-width:900px){",
    "html.sm-app-shell .content{padding-bottom:calc(env(safe-area-inset-bottom,0px) + 74px)}",
    "}",
    "@media screen and (max-width:900px) and (max-height:480px){",
    "html.sm-app-shell .content{padding-bottom:calc(env(safe-area-inset-bottom,0px) + 64px)}",
    "}"
  ].join("");

  /* Champs de saisie du site public : 16 px, seuil en dessous duquel les
     navigateurs de téléphone zooment automatiquement la page au toucher. */
  var CHAMPS_CSS = "@media screen{"
    + "html.sm-app-champs input,html.sm-app-champs select,html.sm-app-champs textarea"
    + "{font-size:16px}"
    + "}";

  function poserCoque() {
    try {
      /* a) Les ecrans de l'application : le cadre ne bouge plus, seule la
            zone de contenu defile. */
      if (document.querySelector(".app")) {
        /* Les zones reservees par le systeme (barre d'etat, barre de gestes)
           ne sont annoncees a la page que si le cadrage « bord a bord » est
           demande. Les pages de l'application sont recopiees telles quelles
           depuis le site : elles ne portent pas cette option, on l'ajoute
           ici, sans toucher au reste de leur cadrage. */
        var meta = document.querySelector('meta[name="viewport"]');
        if (meta) {
          var cadrage = meta.getAttribute("content") || "";
          if (cadrage.indexOf("viewport-fit") === -1) {
            meta.setAttribute("content", cadrage + ", viewport-fit=cover");
          }
        }
        var style = document.createElement("style");
        style.id = "sm-coque-app";
        style.appendChild(document.createTextNode(COQUE_CSS));
        (document.head || document.documentElement).appendChild(style);
        document.documentElement.className += " sm-app-shell";
        return;
      }

      /* b) Le site public, ouvert depuis l'ecran de connexion (lien
            « Autres acces ») : il continue de defiler comme un site, mais
            les champs de saisie passent a 16 px. En dessous de cette
            taille, les navigateurs de telephone zooment la page des que
            l'on touche un champ, et l'on ne voit plus ce que l'on tape. */
      if (document.querySelector(".lp-hero")) {
        var style2 = document.createElement("style");
        style2.id = "sm-coque-site";
        style2.appendChild(document.createTextNode(CHAMPS_CSS));
        (document.head || document.documentElement).appendChild(style2);
        document.documentElement.className += " sm-app-champs";
      }
    } catch (e) {
      /* sans coque : la page garde le comportement du site, elle reste utilisable */
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", poserCoque);
  } else {
    poserCoque();
  }
})();
