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

  /* ---------- Bascule Connexion ↔ Inscription ---------- */
  var vueConnexion = document.getElementById("vueConnexion");
  var vueInscription = document.getElementById("vueInscription");
  var linkInscription = document.getElementById("linkInscription");
  var linkRetourConnexion = document.getElementById("linkRetourConnexion");

  function montrerConnexion() {
    if (vueConnexion) vueConnexion.style.display = "";
    if (vueInscription) vueInscription.style.display = "none";
  }
  function montrerInscription() {
    if (vueConnexion) vueConnexion.style.display = "none";
    if (vueInscription) vueInscription.style.display = "";
    var nom = document.getElementById("nomParent");
    if (nom) nom.focus();
  }
  if (linkInscription) {
    linkInscription.addEventListener("click", function (e) {
      e.preventDefault();
      montrerInscription();
    });
  }
  if (linkRetourConnexion) {
    linkRetourConnexion.addEventListener("click", function (e) {
      e.preventDefault();
      montrerConnexion();
    });
  }

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
})();
