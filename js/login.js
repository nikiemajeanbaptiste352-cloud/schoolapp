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
      info.innerHTML = "<strong>Serveur injoignable.</strong> Démarrez le backend SchoolManager puis ouvrez <b>http://127.0.0.1:8000</b>.";
    }
  }

  if (linkForgot) {
    linkForgot.addEventListener("click", function (e) {
      e.preventDefault();
      alert("Contactez l'administrateur de l'établissement pour réinitialiser votre mot de passe.");
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

  /* ---------- Détection initiale du mode ---------- */
  if (window.API && window.API.enLigne()) {
    window.API.disponible().then(function (ok) {
      modeConnecte = ok;
      texteMode();
    });
  } else {
    modeConnecte = false;
    texteMode();
  }

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

    if (modeConnecte === false) {
      // Backend injoignable (détecté) → pas de connexion fictive possible
      texteMode();
      afficherErreur("Serveur injoignable : connexion impossible.");
      return;
    }
    connexionApi();
  });
})();
