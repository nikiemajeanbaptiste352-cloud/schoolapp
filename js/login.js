/* ============================================================
   SchoolManager — Page de connexion
   ------------------------------------------------------------
   Connexion exclusive au backend FastAPI (POST /api/v1/auth/login).
   Les comptes (rôle, nom, accès) sont définis par l'établissement
   dans la base : aucune donnée fictive n'est acceptée.
   Si le serveur est injoignable, la connexion est impossible et
   le message l'indique clairement.
   ============================================================ */

(function () {
  "use strict";

  // Si déjà connecté, on renvoie vers le tableau de bord
  if (sessionStorage.getItem("sm_session")) {
    window.location.replace("pages/dashboard.html");
    return;
  }

  /* ---------- Indicateur d'état du serveur ---------- */
  var modeConnecte = null; // null = indéterminé, true = API joignable, false = injoignable
  var info = document.getElementById("serveurInfo");
  var linkForgot = document.getElementById("linkForgot");
  // Sur un site distant (Vercel…), le message « démarrez le backend local »
  // n'a pas de sens : on affiche alors une mention de nouvelle tentative.
  var hoteLocal = window.location &&
    (window.location.hostname === "localhost" ||
     window.location.hostname === "127.0.0.1" ||
     window.location.hostname === "::1");

  function texteMode() {
    if (!info) return;
    if (modeConnecte === true) {
      info.className = "alert alert-info";
      info.innerHTML = "<strong>Serveur connecté.</strong> Utilisez les identifiants fournis par votre établissement.";
    } else if (modeConnecte === false) {
      info.className = "alert";
      info.style.color = "#b91c1c";
      info.style.background = "#fef2f2";
      info.style.borderColor = "#fecaca";
      info.innerHTML = hoteLocal
        ? "<strong>Serveur injoignable.</strong> Démarrez le backend SchoolManager puis ouvrez <b>http://127.0.0.1:8000</b>."
        : "<strong>Serveur injoignable.</strong> Le serveur ne répond pas encore — nouvelle tentative automatique…";
    }
  }

  if (linkForgot) {
    linkForgot.addEventListener("click", function (e) {
      e.preventDefault();
      alert("Contactez l'administrateur de l'établissement pour réinitialiser votre mot de passe.");
    });
  }

  /* ---------- Bascule Connexion ↔ Inscription (Établissement / Parent) ↔ Code email ---------- */
  var vueConnexion = document.getElementById("vueConnexion");
  var vueInscription = document.getElementById("vueInscription");
  var vueInscriptionEtab = document.getElementById("vueInscriptionEtab");
  var vueCode = document.getElementById("vueCode");
  var linkInscription = document.getElementById("linkInscription");
  var linkRetourConnexion = document.getElementById("linkRetourConnexion");
  var linkInscriptionEtab = document.getElementById("linkInscriptionEtab");
  var linkRetourEtab = document.getElementById("linkRetourEtab");
  var linkCode = document.getElementById("linkCode");
  var linkRetourCode = document.getElementById("linkRetourCode");

  function cacherVues() {
    if (vueConnexion) vueConnexion.style.display = "none";
    if (vueInscription) vueInscription.style.display = "none";
    if (vueInscriptionEtab) vueInscriptionEtab.style.display = "none";
    if (vueCode) vueCode.style.display = "none";
  }
  function montrerConnexion() {
    cacherVues();
    if (vueConnexion) vueConnexion.style.display = "";
  }
  function montrerInscription() {
    cacherVues();
    if (vueInscription) vueInscription.style.display = "";
    var nom = document.getElementById("nomParent");
    if (nom) nom.focus();
  }
  function montrerInscriptionEtab() {
    cacherVues();
    if (vueInscriptionEtab) vueInscriptionEtab.style.display = "";
    var ecole = document.getElementById("ecoleEtab");
    if (ecole) ecole.focus();
  }
  function montrerCode() {
    cacherVues();
    if (vueCode) vueCode.style.display = "";
    reinitialiserVueCode(true);
    var email = document.getElementById("emailCode");
    if (email) email.focus();
  }

  /* ---------- Choix du profil d'entrée : « Établissement » ou « Parent » ---------- */
  var profilActuel = "etablissement"; // "etablissement" | "parent"
  var btnModeEtab = document.getElementById("btnModeEtab");
  var btnModeParent = document.getElementById("btnModeParent");
  var lcTitreConnexion = document.getElementById("lcTitreConnexion");
  var lcSousConnexion = document.getElementById("lcSousConnexion");
  var actionEtab = document.getElementById("actionEtab");
  var actionParent = document.getElementById("actionParent");
  var TITRES_CONNEXION = {
    etablissement: {
      titre: "Espace Établissement 🏫",
      sous: "Connexion de la direction et de l'équipe de votre école — utilisez les identifiants fournis par l'établissement."
    },
    parent: {
      titre: "Bon retour 👋",
      sous: "Connectez-vous pour accéder à votre espace."
    }
  };

  // Applique l'apparence de la carte de connexion selon le profil choisi
  // (titre, lien contextuel, méthodes Google / code email réservées aux parents).
  function appliquerAffichageProfil() {
    var etab = profilActuel === "etablissement";
    var opts = optionsAuthMemorisees || {};
    if (lcTitreConnexion) lcTitreConnexion.textContent = TITRES_CONNEXION[profilActuel].titre;
    if (lcSousConnexion) lcSousConnexion.textContent = TITRES_CONNEXION[profilActuel].sous;
    if (btnModeEtab) {
      btnModeEtab.classList.toggle("is-actif", etab);
      btnModeEtab.setAttribute("aria-selected", etab ? "true" : "false");
    }
    if (btnModeParent) {
      btnModeParent.classList.toggle("is-actif", !etab);
      btnModeParent.setAttribute("aria-selected", etab ? "false" : "true");
    }
    if (actionEtab) { if (etab) actionEtab.removeAttribute("hidden"); else actionEtab.setAttribute("hidden", ""); }
    if (actionParent) { if (etab) actionParent.setAttribute("hidden", ""); else actionParent.removeAttribute("hidden"); }
    if (zoneGoogle) zoneGoogle.style.display = (!etab && opts.google) ? "" : "none";
    if (zoneCode) zoneCode.style.display = (!etab && opts.code_email) ? "" : "none";
  }

  // Bascule vers le profil demandé puis revient à l'écran de connexion.
  function definirProfil(p) {
    if (p !== "etablissement" && p !== "parent") return;
    profilActuel = p;
    appliquerAffichageProfil();
    montrerConnexion();
  }
  if (btnModeEtab) {
    btnModeEtab.addEventListener("click", function (e) {
      e.preventDefault();
      definirProfil("etablissement");
    });
  }
  if (btnModeParent) {
    btnModeParent.addEventListener("click", function (e) {
      e.preventDefault();
      definirProfil("parent");
    });
  }
  if (linkInscription) {
    linkInscription.addEventListener("click", function (e) {
      e.preventDefault();
      definirProfil("parent");
      montrerInscription();
    });
  }
  if (linkInscriptionEtab) {
    linkInscriptionEtab.addEventListener("click", function (e) {
      e.preventDefault();
      definirProfil("etablissement");
      montrerInscriptionEtab();
    });
  }
  if (linkRetourConnexion) {
    linkRetourConnexion.addEventListener("click", function (e) {
      e.preventDefault();
      montrerConnexion();
    });
  }
  if (linkRetourEtab) {
    linkRetourEtab.addEventListener("click", function (e) {
      e.preventDefault();
      montrerConnexion();
    });
  }
  if (linkCode) {
    linkCode.addEventListener("click", function (e) {
      e.preventDefault();
      montrerCode();
    });
  }
  if (linkRetourCode) {
    linkRetourCode.addEventListener("click", function (e) {
      e.preventDefault();
      montrerConnexion();
    });
  }

  /* ---------- Méthodes optionnelles (Google / code email) ----------
     La page interroge /auth/options pour n'afficher que les méthodes
     réellement configurées sur le serveur. */
  var zoneGoogle = document.getElementById("zoneGoogle");
  var btnGoogle = document.getElementById("btnGoogle");
  var zoneCode = document.getElementById("zoneCode");
  var optionsAuthMemorisees = null;   // {google, code_email} — options reçues du serveur

  if (btnGoogle && window.API && window.API.urlConnexionGoogle) {
    btnGoogle.addEventListener("click", function () {
      btnGoogle.disabled = true;
      btnGoogle.textContent = "Redirection vers Google…";
      window.location.href = window.API.urlConnexionGoogle();
    });
  }
  function appliquerOptionsAuth() {
    if (!window.API || !window.API.optionsAuth) return;
    window.API.optionsAuth().then(function (o) {
      optionsAuthMemorisees = o || {};
      appliquerAffichageProfil(); // réaffiche selon le profil Établissement / Parent
    }).catch(function () { /* silencieux : méthodes laissées masquées */ });
  }
  appliquerOptionsAuth();
  appliquerAffichageProfil();

  /* ---------- Validation ---------- */
  var form = document.getElementById("loginForm");
  var inputEmail = document.getElementById("email");
  var inputMdp = document.getElementById("mdp");
  var errEmail = document.getElementById("errEmail");
  var errMdp = document.getElementById("errMdp");
  var btnLogin = document.getElementById("btnLogin");

  function invalid(input, errEl) {
    input.classList.add("invalid");
    errEl.classList.add("show");
  }
  function ok(input, errEl) {
    input.classList.remove("invalid");
    errEl.classList.remove("show");
  }
  function afficherErreur(msg) {
    errEmail.textContent = msg;
    errEmail.classList.add("show");
    inputEmail.classList.add("invalid");
  }

  inputEmail.addEventListener("input", function () { ok(inputEmail, errEmail); });
  inputMdp.addEventListener("input", function () { ok(inputMdp, errMdp); });

  /* ---------- Détection initiale du mode ----------
     Le premier appel peut réveiller un backend « serverless » (Vercel), dont
     le démarrage dépasse parfois le délai d'attente du ping : on réessaie
     quelques fois avant de conclure à une panne. */
  var essaies = 0;
  function verifierServeur() {
    if (!window.API || !window.API.enLigne()) {
      modeConnecte = false;
      texteMode();
      return;
    }
    window.API.disponible().then(function (ok) {
      modeConnecte = ok;
      texteMode();
      if (!ok && essaies < 5) {
        essaies += 1;
        setTimeout(verifierServeur, 2500);
      }
    });
  }
  verifierServeur();

  /* ---------- Connexion (API uniquement) ---------- */
  function connexionApi() {
    var email = inputEmail.value.trim();
    var mdp = inputMdp.value;
    btnLogin.disabled = true;
    btnLogin.textContent = "Connexion…";

    window.API.connexion(email, mdp).then(function (data) {
      modeConnecte = true;
      texteMode();
      var user = data.user || {};
      sessionStorage.setItem("sm_session", JSON.stringify({
        role: user.role || "Administrateur",
        email: user.email || email,
        nom: user.nom || ""
      }));
      window.location.href = "pages/dashboard.html";
    }).catch(function (err) {
      btnLogin.disabled = false;
      btnLogin.textContent = "Se connecter →";
      if (err && err.reseau) {
        // Serveur injoignable → aucune connexion fictive possible
        modeConnecte = false;
        texteMode();
        afficherErreur("Serveur injoignable : démarrez le backend puis réessayez.");
      } else {
        if (modeConnecte === null) { modeConnecte = true; texteMode(); }
        afficherErreur((err && err.detail) || "Connexion impossible.");
      }
    });
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var email = inputEmail.value.trim();
    var mdp = inputMdp.value;
    var valid = true;

    if (!email) { invalid(inputEmail, errEmail); valid = false; }
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      invalid(inputEmail, errEmail);
      errEmail.textContent = "Format d'email invalide (ex. nom@exemple.com).";
      errEmail.classList.add("show");
      valid = false;
    }
    if (!mdp) { invalid(inputMdp, errMdp); valid = false; }
    if (!valid) return;

    // Même si le serveur semblait injoignable, on tente la vraie requête : si
    // le backend a fini de démarrer (serverless), elle réussit ; sinon
    // connexionApi() affichera l'erreur réseau. Aucune donnée fictive.
    connexionApi();
  });

  /* ---------- Inscription (compte Parent, API uniquement) ---------- */
  var formInscription = document.getElementById("inscriptionForm");
  if (formInscription) {
    var nomParent = document.getElementById("nomParent");
    var emailParent = document.getElementById("emailParent");
    var mdpParent = document.getElementById("mdpParent");
    var mdpParent2 = document.getElementById("mdpParent2");
    var errNomParent = document.getElementById("errNomParent");
    var errEmailParent = document.getElementById("errEmailParent");
    var errMdpParent = document.getElementById("errMdpParent");
    var errMdpParent2 = document.getElementById("errMdpParent2");
    var errInscription = document.getElementById("errInscription");
    var btnInscription = document.getElementById("btnInscription");

    function okInscription(input, errEl) {
      input.classList.remove("invalid");
      if (errEl) errEl.classList.remove("show");
    }
    function invalideInscription(input, errEl, message) {
      input.classList.add("invalid");
      if (errEl) {
        errEl.textContent = message || errEl.textContent;
        errEl.classList.add("show");
      }
    }

    nomParent.addEventListener("input", function () { okInscription(nomParent, errNomParent); });
    emailParent.addEventListener("input", function () { okInscription(emailParent, errEmailParent); });
    mdpParent.addEventListener("input", function () { okInscription(mdpParent, errMdpParent); });
    mdpParent2.addEventListener("input", function () { okInscription(mdpParent2, errMdpParent2); });

    function inscriptionApi() {
      btnInscription.disabled = true;
      btnInscription.textContent = "Création du compte…";
      if (errInscription) { errInscription.classList.remove("show"); }

      window.API.inscription(
        nomParent.value.trim(),
        emailParent.value.trim(),
        mdpParent.value
      ).then(function (data) {
        // L'API renvoie un jeton → l'utilisateur est connecté.
        var user = data.user || {};
        sessionStorage.setItem("sm_session", JSON.stringify({
          role: user.role || "Parent",
          email: user.email || emailParent.value.trim(),
          nom: user.nom || ""
        }));
        window.location.href = "pages/dashboard.html";
      }).catch(function (err) {
        btnInscription.disabled = false;
        btnInscription.textContent = "Créer mon compte →";
        var msg = "Inscription impossible.";
        if (err && err.reseau) {
          msg = "Serveur injoignable : démarrez le backend puis réessayez.";
        } else if (err && err.detail) {
          msg = err.detail;
        }
        if (errInscription) {
          errInscription.textContent = msg;
          errInscription.classList.add("show");
        } else {
          alert(msg);
        }
      });
    }

    formInscription.addEventListener("submit", function (e) {
      e.preventDefault();
      var nom = nomParent.value.trim();
      var email = emailParent.value.trim();
      var mdp = mdpParent.value;
      var mdp2 = mdpParent2.value;
      var valide = true;

      if (!nom) { invalideInscription(nomParent, errNomParent, "Veuillez saisir votre nom complet."); valide = false; }
      else { okInscription(nomParent, errNomParent); }

      if (!email) { invalideInscription(emailParent, errEmailParent, "Veuillez saisir votre adresse email."); valide = false; }
      else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
        invalideInscription(emailParent, errEmailParent, "Format d'email invalide (ex. nom@exemple.com).");
        valide = false;
      } else { okInscription(emailParent, errEmailParent); }

      if (mdp.length < 6) { invalideInscription(mdpParent, errMdpParent, "Le mot de passe doit contenir au moins 6 caractères."); valide = false; }
      else { okInscription(mdpParent, errMdpParent); }

      if (!mdp2) { invalideInscription(mdpParent2, errMdpParent2, "Veuillez confirmer votre mot de passe."); valide = false; }
      else if (mdp2 !== mdp) { invalideInscription(mdpParent2, errMdpParent2, "Les deux mots de passe ne correspondent pas."); valide = false; }
      else { okInscription(mdpParent2, errMdpParent2); }

      if (!valide) return;
      inscriptionApi();
    });
  }

  /* ---------- Inscription (espace Établissement, API uniquement) ---------- */
  var formInscriptionEtab = document.getElementById("inscriptionEtabForm");
  if (formInscriptionEtab) {
    var ecoleEtab = document.getElementById("ecoleEtab");
    var nomEtab = document.getElementById("nomEtab");
    var emailEtab = document.getElementById("emailEtab");
    var mdpEtab = document.getElementById("mdpEtab");
    var mdpEtab2 = document.getElementById("mdpEtab2");
    var errEcoleEtab = document.getElementById("errEcoleEtab");
    var errNomEtab = document.getElementById("errNomEtab");
    var errEmailEtab = document.getElementById("errEmailEtab");
    var errMdpEtab = document.getElementById("errMdpEtab");
    var errMdpEtab2 = document.getElementById("errMdpEtab2");
    var errInscriptionEtab = document.getElementById("errInscriptionEtab");
    var btnInscriptionEtab = document.getElementById("btnInscriptionEtab");

    function okEtab(input, errEl) {
      input.classList.remove("invalid");
      if (errEl) errEl.classList.remove("show");
    }
    function invalideEtab(input, errEl, message) {
      input.classList.add("invalid");
      if (errEl) {
        errEl.textContent = message || errEl.textContent;
        errEl.classList.add("show");
      }
    }

    ecoleEtab.addEventListener("input", function () { okEtab(ecoleEtab, errEcoleEtab); });
    nomEtab.addEventListener("input", function () { okEtab(nomEtab, errNomEtab); });
    emailEtab.addEventListener("input", function () { okEtab(emailEtab, errEmailEtab); });
    mdpEtab.addEventListener("input", function () { okEtab(mdpEtab, errMdpEtab); });
    mdpEtab2.addEventListener("input", function () { okEtab(mdpEtab2, errMdpEtab2); });

    function inscriptionEtabApi() {
      btnInscriptionEtab.disabled = true;
      btnInscriptionEtab.textContent = "Création du compte…";
      if (errInscriptionEtab) { errInscriptionEtab.classList.remove("show"); }

      window.API.inscriptionEtablissement(
        ecoleEtab.value.trim(),
        nomEtab.value.trim(),
        emailEtab.value.trim(),
        mdpEtab.value
      ).then(function (data) {
        // L'API renvoie un jeton → l'utilisateur (Administrateur) est connecté.
        var user = data.user || {};
        sessionStorage.setItem("sm_session", JSON.stringify({
          role: user.role || "Administrateur",
          email: user.email || emailEtab.value.trim(),
          nom: user.nom || ""
        }));
        window.location.href = "pages/dashboard.html";
      }).catch(function (err) {
        btnInscriptionEtab.disabled = false;
        btnInscriptionEtab.textContent = "Créer le compte de l'établissement →";
        var msg = "Inscription impossible.";
        if (err && err.reseau) {
          msg = "Serveur injoignable : démarrez le backend puis réessayez.";
        } else if (err && err.detail) {
          msg = err.detail;
        }
        if (errInscriptionEtab) {
          errInscriptionEtab.textContent = msg;
          errInscriptionEtab.classList.add("show");
        } else {
          alert(msg);
        }
      });
    }

    formInscriptionEtab.addEventListener("submit", function (e) {
      e.preventDefault();
      var ecole = ecoleEtab.value.trim();
      var nom = nomEtab.value.trim();
      var email = emailEtab.value.trim();
      var mdp = mdpEtab.value;
      var mdp2 = mdpEtab2.value;
      var valide = true;

      if (!ecole) { invalideEtab(ecoleEtab, errEcoleEtab, "Veuillez saisir le nom de l'établissement."); valide = false; }
      else { okEtab(ecoleEtab, errEcoleEtab); }

      if (!nom) { invalideEtab(nomEtab, errNomEtab, "Veuillez saisir votre nom."); valide = false; }
      else { okEtab(nomEtab, errNomEtab); }

      if (!email) { invalideEtab(emailEtab, errEmailEtab, "Veuillez saisir votre adresse email."); valide = false; }
      else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
        invalideEtab(emailEtab, errEmailEtab, "Format d'email invalide (ex. nom@exemple.com).");
        valide = false;
      } else { okEtab(emailEtab, errEmailEtab); }

      if (mdp.length < 6) { invalideEtab(mdpEtab, errMdpEtab, "Le mot de passe doit contenir au moins 6 caractères."); valide = false; }
      else { okEtab(mdpEtab, errMdpEtab); }

      if (!mdp2) { invalideEtab(mdpEtab2, errMdpEtab2, "Veuillez confirmer votre mot de passe."); valide = false; }
      else if (mdp2 !== mdp) { invalideEtab(mdpEtab2, errMdpEtab2, "Les deux mots de passe ne correspondent pas."); valide = false; }
      else { okEtab(mdpEtab2, errMdpEtab2); }

      if (!valide) return;
      inscriptionEtabApi();
    });
  }

  /* ---------- Connexion par code email (sans mot de passe) ---------- */
  var formCode = document.getElementById("codeForm");
  var nomCode = document.getElementById("nomCode");
  var emailCode = document.getElementById("emailCode");
  var errEmailCode = document.getElementById("errEmailCode");
  var btnDemanderCode = document.getElementById("btnDemanderCode");
  var errCodeDemande = document.getElementById("errCodeDemande");
  var zoneSaisieCode = document.getElementById("zoneSaisieCode");
  var infoCodeEnvoye = document.getElementById("infoCodeEnvoye");
  var saisieCode = document.getElementById("saisieCode");
  var errSaisieCode = document.getElementById("errSaisieCode");
  var btnValiderCode = document.getElementById("btnValiderCode");
  var linkRenvoiCode = document.getElementById("linkRenvoiCode");
  var errCodeGlobal = document.getElementById("errCodeGlobal");
  var emailEnCours = "";
  var nomEnCours = "";

  function masquerErreursCode() {
    var els = [errEmailCode, errCodeDemande, errSaisieCode, errCodeGlobal];
    for (var i = 0; i < els.length; i++) {
      if (els[i]) els[i].classList.remove("show");
    }
    if (emailCode) emailCode.classList.remove("invalid");
    if (saisieCode) saisieCode.classList.remove("invalid");
  }
  function erreurChampCode(input, errEl, message) {
    if (input) input.classList.add("invalid");
    if (errEl) {
      errEl.textContent = message || errEl.textContent;
      errEl.classList.add("show");
    }
  }
  function reinitialiserVueCode(tout) {
    emailEnCours = "";
    nomEnCours = "";
    masquerErreursCode();
    if (zoneSaisieCode) zoneSaisieCode.style.display = "none";
    if (saisieCode) saisieCode.value = "";
    if (btnDemanderCode) {
      btnDemanderCode.disabled = false;
      btnDemanderCode.textContent = "Recevoir le code par email →";
    }
    if (btnValiderCode) {
      btnValiderCode.disabled = false;
      btnValiderCode.textContent = "Valider et me connecter →";
    }
    if (emailCode) emailCode.disabled = false;
    if (nomCode) nomCode.disabled = false;
    if (tout) {
      if (emailCode) emailCode.value = "";
      if (nomCode) nomCode.value = "";
    }
  }

  if (emailCode) {
    emailCode.addEventListener("input", function () {
      emailCode.classList.remove("invalid");
      if (errEmailCode) errEmailCode.classList.remove("show");
    });
  }
  if (saisieCode) {
    saisieCode.addEventListener("input", function () {
      saisieCode.classList.remove("invalid");
      if (errSaisieCode) errSaisieCode.classList.remove("show");
    });
  }

  function demanderCodeApi() {
    if (!btnDemanderCode || !emailCode) return;
    var email = emailCode.value.trim();
    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      erreurChampCode(emailCode, errEmailCode, "Veuillez saisir une adresse email valide.");
      emailCode.focus();
      return;
    }
    nomEnCours = (nomCode && nomCode.value.trim()) || "";
    btnDemanderCode.disabled = true;
    btnDemanderCode.textContent = "Envoi du code…";
    masquerErreursCode();

    window.API.demanderCode(email, nomEnCours).then(function (data) {
      emailEnCours = email;
      btnDemanderCode.disabled = false;
      btnDemanderCode.textContent = "Recevoir le code par email →";
      // L'email reste verrouillé pendant la saisie du code.
      emailCode.disabled = true;
      if (nomCode) nomCode.disabled = true;
      if (zoneSaisieCode) zoneSaisieCode.style.display = "";
      if (infoCodeEnvoye) {
        infoCodeEnvoye.innerHTML =
          "<strong>Code envoyé à " + emailCode.value.replace(/</g, "&lt;") +
          ".</strong> Vérifiez votre boîte mail (dont les courriers " +
          "indésirables) — il est valable 10 minutes.";
      }
      if (saisieCode) saisieCode.focus();
    }).catch(function (err) {
      btnDemanderCode.disabled = false;
      btnDemanderCode.textContent = "Recevoir le code par email →";
      var msg = (err && err.detail) || "Envoi impossible.";
      if (err && err.reseau) msg = "Serveur injoignable : démarrez le backend puis réessayez.";
      erreurChampCode(null, errCodeDemande, msg);
    });
  }

  function validerCodeApi() {
    if (!btnValiderCode) return;
    var code = (saisieCode && saisieCode.value.trim()) || "";
    if (!/^\d{6}$/.test(code)) {
      erreurChampCode(saisieCode, errSaisieCode, "Saisissez le code à 6 chiffres reçu par email.");
      if (saisieCode) saisieCode.focus();
      return;
    }
    btnValiderCode.disabled = true;
    btnValiderCode.textContent = "Connexion…";
    masquerErreursCode();

    window.API.validerCode(emailEnCours, code, nomEnCours).then(function (data) {
      var user = data.user || {};
      sessionStorage.setItem("sm_session", JSON.stringify({
        role: user.role || "Parent",
        email: user.email || emailEnCours,
        nom: user.nom || ""
      }));
      window.location.href = "pages/dashboard.html";
    }).catch(function (err) {
      btnValiderCode.disabled = false;
      btnValiderCode.textContent = "Valider et me connecter →";
      var msg = (err && err.detail) || "Connexion impossible.";
      if (err && err.reseau) msg = "Serveur injoignable : démarrez le backend puis réessayez.";
      if (err && err.statut === 401) {
        erreurChampCode(saisieCode, errSaisieCode, msg);
      } else {
        erreurChampCode(null, errCodeGlobal, msg);
      }
    });
  }

  if (formCode) {
    formCode.addEventListener("submit", function (e) {
      e.preventDefault();
      demanderCodeApi();
    });
  }
  if (btnValiderCode) {
    btnValiderCode.addEventListener("click", function () {
      validerCodeApi();
    });
  }
  if (saisieCode) {
    saisieCode.addEventListener("keydown", function (e) {
      if (e.key === "Enter") {
        e.preventDefault();
        validerCodeApi();
      }
    });
  }
  if (linkRenvoiCode) {
    linkRenvoiCode.addEventListener("click", function (e) {
      e.preventDefault();
      if (emailEnCours) {
        if (emailCode) emailCode.value = emailEnCours;
        if (nomCode) nomCode.value = nomEnCours;
        masquerErreursCode();
        demanderCodeApi();
      }
    });
  }
})();
