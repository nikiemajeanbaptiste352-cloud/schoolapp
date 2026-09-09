/* ============================================================
   SchoolManager — ✍️ Ma présence (enseignant)
   Cahier de présence numérique : l'enseignant signe ses séances
   de cours réellement données ; le relevé du mois est imprimable
   et sert au calcul de sa rémunération (fiche de paie).
   ============================================================ */

(function () {
  "use strict";

  var SM = window.SM;
  var API = window.API;

  // Accès réservé au Professeur lié à sa fiche enseignant.
  var sess = SM.getSession();
  if (!sess || sess.role !== "Professeur") {
    window.location.replace("../index.html");
    return;
  }

  function el(id) { return document.getElementById(id); }

  var MOIS_NOMS = ["janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre"];
  function libelleMois(mois) {
    if (!mois || mois.length !== 7) return mois || "";
    var annee = mois.slice(0, 4);
    var m = parseInt(mois.slice(5, 7), 10) - 1;
    var nom = MOIS_NOMS[m] ? MOIS_NOMS[m] : "";
    return nom ? nom.charAt(0).toUpperCase() + nom.slice(1) + " " + annee : mois;
  }
  function isoAujourdhui() {
    var d = new Date();
    return d.getFullYear() + "-" + ("0" + (d.getMonth() + 1)).slice(-2) + "-" + ("0" + d.getDate()).slice(-2);
  }
  function fmtDuree(h) {
    if (h === null || h === undefined || isNaN(h)) return "—";
    var total = Math.round(Number(h) * 60);
    var hh = Math.floor(total / 60);
    var mm = total % 60;
    return hh + " h " + ("0" + mm).slice(-2);
  }
  function minutesDe(v) {
    var m = /^(\d{2}):(\d{2})$/.exec(v || "");
    return m ? parseInt(m[1], 10) * 60 + parseInt(m[2], 10) : null;
  }
  function calculerHeures(debut, fin) {
    var a = minutesDe(debut), b = minutesDe(fin);
    if (a === null || b === null || b <= a) return null;
    return Math.round((b - a) / 6) / 10; // arrondi à 0,1 h près
  }

  /* ---------- État ---------- */
  var profil = null;       // GET /mon-espace/profil
  var fiches = [];         // GET /mon-espace/fiches (tous les mois)
  var etatMois = null;     // GET /mon-espace/seances?mois=…
  var moisSel = null;      // mois affiché (AAAA-MM)
  var seanceDel = null;    // séance à annuler

  function ficheDuMois(mois) {
    for (var i = 0; i < fiches.length; i++) {
      if (fiches[i].mois === mois) return fiches[i];
    }
    return null;
  }

  function erreur(e) {
    var msg = (e && e.detail) ? e.detail : (e && e.message) ? e.message : "Erreur inconnue.";
    SM.toast(String(msg), "error");
  }

  /* ---------- Compteurs ---------- */
  function compteurs() {
    var d = etatMois || { nbSeances: 0, heuresTotal: 0, seances: [] };
    var jours = {};
    d.seances.forEach(function (s) { jours[s.date] = true; });
    el("miniCounts").innerHTML =
      '<div class="mini-stat"><div class="v">' + fmtDuree(d.heuresTotal) + '</div><div class="l">Heures signées</div></div>' +
      '<div class="mini-stat"><div class="v">' + d.nbSeances + '</div><div class="l">Séances signées</div></div>' +
      '<div class="mini-stat"><div class="v">' + Object.keys(jours).length + '</div><div class="l">Jours travaillés</div></div>' +
      '<div class="mini-stat"><div class="v">' + SM.formatFCFA(profil.tauxHoraire).replace(" FCFA", "") + '</div><div class="l">Taux horaire</div></div>';
  }

  /* ---------- Rendu du cahier ---------- */
  function render() {
    var tbody = el("tableBody");
    var liste = etatMois ? etatMois.seances : [];
    var fiche = ficheDuMois(moisSel);
    var clos = fiche !== null; // une fiche existe : le mois est clôturé (gel)
    var payee = fiche !== null && fiche.statut === "payee";

    // Bouton « Signer » : masqué une fois le mois réglé.
    el("btnSigner").style.display = payee ? "none" : "";
    el("btnPrint").style.display = "";

    // Note d'état du mois
    var note = el("noteMois");
    if (payee) {
      note.style.display = "";
      note.innerHTML = '<div class="alert alert-success">🔒 <div><strong>Mois réglé :</strong> votre fiche de ' + SM.escapeHtml(libelleMois(moisSel)) +
        ' a été payée' + (fiche.payeeLe ? " le " + SM.escapeHtml(String(fiche.payeeLe).split(" ")[0]) : "") +
        ". Ce cahier est clos : plus aucune séance ne peut être ajoutée ni annulée.</div></div>";
    } else if (fiche) {
      note.style.display = "";
      note.innerHTML = '<div class="alert alert-warning">🧾 <div><strong>Fiche générée :</strong> votre relevé de ' + SM.escapeHtml(libelleMois(moisSel)) +
        " est enregistré (en attente de paiement). Les séances de ce mois ne peuvent plus être annulées.</div></div>";
    } else {
      note.style.display = "none";
      note.innerHTML = "";
    }

    if (!liste.length) {
      tbody.innerHTML =
        '<tr><td colspan="7"><div class="empty-state"><div class="e-ico">✍️</div><h4>Aucune séance signée ce mois</h4>' +
        "<p>Signez vos cours réellement donnés : ils alimentent votre relevé de présence.</p></div></td></tr>";
      el("countLabel").textContent = "0 séance signée en " + libelleMois(moisSel);
      return;
    }

    tbody.innerHTML = liste.map(function (s) {
      var actions;
      if (clos) {
        actions = '<span class="text-muted text-sm">🔒 Clôturé</span>';
      } else {
        actions = '<button class="btn-icon danger" title="Annuler cette signature" data-del="' + s.id + '">🗑️</button>';
      }
      return (
        "<tr>" +
        "  <td class='fw-600'>" + SM.fmtDate(s.date) + "</td>" +
        "  <td><span class='fw-600'>" + SM.escapeHtml(s.heureDebut) + " – " + SM.escapeHtml(s.heureFin) + "</span></td>" +
        "  <td>" + SM.escapeHtml(s.matiereNom) + "</td>" +
        "  <td><span class='chip-plain'>" + SM.escapeHtml(s.classeNom) + "</span></td>" +
        "  <td>" + fmtDuree(s.heures) + "</td>" +
        "  <td class='text-muted text-sm'>" + SM.escapeHtml(String(s.creeLe || "").replace(" ", " à ")) + "</td>" +
        '  <td><div class="row-actions" style="justify-content:center">' + actions + "</div></td>" +
        "</tr>"
      );
    }).join("");
    el("countLabel").textContent =
      liste.length + " séance" + (liste.length > 1 ? "s" : "") + " signée" + (liste.length > 1 ? "s" : "") + " en " + libelleMois(moisSel);
  }

  function afficher() {
    compteurs();
    render();
  }

  /* ---------- Chargement serveur ---------- */
  function chargerMois(mois) {
    moisSel = mois || moisSel;
    el("moisInput").value = moisSel;
    return API.mesSeances(moisSel)
      .then(function (d) { etatMois = d; afficher(); })
      .catch(erreur);
  }

  function chargerTout() {
    API.monEspaceProfil()
      .then(function (p) {
        profil = p;
        return API.mesFiches().then(function (f) { fiches = f.fiches || []; });
      })
      .then(function () {
        remplirModal();
        var moisParDefaut = profil.mois; // mois courant côté serveur
        el("moisInput").value = moisParDefaut;
        return chargerMois(moisParDefaut);
      })
      .catch(function (e) {
        if (e && e.statut === 403) {
          SM.toast("Votre compte n'est pas lié à une fiche enseignant. Contactez l'administration.", "error");
        } else {
          erreur(e);
        }
      });
  }

  /* ---------- Modale signer ---------- */
  function remplirModal() {
    var ens = profil.enseignant || {};
    el("fMatiere").value = ens.matiereNom || "—";
    el("fDate").max = isoAujourdhui();

    var selClasse = el("fClasse");
    selClasse.innerHTML = '<option value="">Choisir une classe…</option>';
    (ens.classes || []).forEach(function (c) {
      var o = document.createElement("option");
      o.value = c.id;
      o.textContent = c.nom + (c.cycle ? " (" + c.cycle + ")" : "");
      selClasse.appendChild(o);
    });
    if (ens.classes && ens.classes.length === 1) selClasse.value = ens.classes[0].id;
    majDuree();
  }

  function majDuree() {
    var t = calculerHeures(el("fDebut").value, el("fFin").value);
    el("fDuree").textContent = t === null ? "—" : fmtDuree(t);
  }

  function montrerErreurs(champs) {
    ["errDate", "errClasse", "errHeures"].forEach(function (id) { el(id).classList.remove("show"); });
    champs.forEach(function (id) { el(id).classList.add("show"); });
  }

  function sauverSeance() {
    var date = el("fDate").value;
    var classe = el("fClasse").value;
    var debut = el("fDebut").value;
    var fin = el("fFin").value;
    var heures = calculerHeures(debut, fin);
    var errs = [];
    if (!date || date > isoAujourdhui()) errs.push("errDate");
    if (!classe) errs.push("errClasse");
    if (heures === null) errs.push("errHeures");
    if (errs.length) { montrerErreurs(errs); return; }
    montrerErreurs([]);

    API.signerSeance({
      date: date,
      classe_id: classe,
      matiere_id: profil.enseignant.matiereId || null,
      heure_debut: debut,
      heure_fin: fin
    }).then(function (s) {
      SM.toast("Séance signée : " + SM.fmtDate(s.date) + " (" + s.classeNom + ", " + s.heureDebut + " – " + s.heureFin + ")", "success");
      SM.closeModal("modalSeance");
      el("fDate").value = "";
      return chargerMois(moisSel);
    }).catch(erreur);
  }

  /* ---------- Annulation ---------- */
  function confirmerAnnulation() {
    if (!seanceDel) return;
    API.annulerSeance(seanceDel.id)
      .then(function () {
        SM.toast("Séance annulée. Le relevé a été mis à jour.", "success");
        SM.closeModal("modalDel");
        seanceDel = null;
        return chargerMois(moisSel);
      })
      .catch(erreur);
  }

  /* ---------- Impression du relevé ---------- */
  function construireReleve() {
    var ens = (profil && profil.enseignant) || {};
    var d = etatMois || { seances: [], nbSeances: 0, heuresTotal: 0 };
    var annee = SD && SD.ecole && SD.ecole.annee ? SD.ecole.annee : "";

    var lignes = d.seances.map(function (s, i) {
      return (
        "<tr>" +
        "  <td style='text-align:center'>" + (i + 1) + "</td>" +
        "  <td>" + SM.fmtDate(s.date) + "</td>" +
        "  <td>" + SM.escapeHtml(s.classeNom) + "</td>" +
        "  <td>" + SM.escapeHtml(s.heureDebut) + " à " + SM.escapeHtml(s.heureFin) + "</td>" +
        "  <td>" + SM.escapeHtml(s.matiereNom) + "</td>" +
        "  <td style='text-align:right'>" + fmtDuree(s.heures) + "</td>" +
        "  <td><div>" + SM.escapeHtml(ens.prenom + " " + ens.nom) + '</div><div class="text-muted" style="font-size:11px">Signé le ' + SM.escapeHtml(String(s.creeLe || "").replace(" ", " à ")) + "</div></td>" +
        "</tr>"
      );
    }).join("");

    var vides = "";
    if (!d.seances.length) {
      var nb = 6;
      for (var k = 0; k < nb; k++) {
        vides += '<tr><td style="text-align:center">' + (k + 1) + '</td><td colspan="5"></td><td></td></tr>';
      }
    }

    el("relevePrint").innerHTML =
      '<div class="print-area">' +
      '<div class="bulletin">' +
      '  <div class="bulletin-head">' +
      '    <img class="logo" src="../assets/logo.svg" alt="Logo">' +
      "    <div>" +
      '      <div class="school-name">' + SM.escapeHtml((SD && SD.ecole ? SD.ecole.nom : "") || "Établissement") + "</div>" +
      '      <div class="school-sub">' + (annee ? "Année scolaire " + SM.escapeHtml(annee) + " · " : "") + "Cahier de présence des enseignants</div>" +
      "    </div>" +
      "  </div>" +
      '  <div class="bulletin-title">RELEVÉ MENSUEL DE PRÉSENCE — ' + SM.escapeHtml(libelleMois(moisSel).toUpperCase()) + "</div>" +
      '  <div class="bulletin-info">' +
      '    <div><span class="text-muted">Enseignant(e)</span><br><strong>' + SM.escapeHtml(ens.prenom + " " + ens.nom) + "</strong></div>" +
      '    <div><span class="text-muted">Matière</span><br><strong>' + SM.escapeHtml(ens.matiereNom || "—") + "</strong></div>" +
      '    <div><span class="text-muted">Taux horaire</span><br><strong>' + SM.formatFCFA(profil.tauxHoraire) + "</strong></div>" +
      "  </div>" +
      "  <table>" +
      "    <thead><tr><th>N°</th><th>Date</th><th>Classe</th><th>Horaires</th><th>Matière</th><th style='text-align:right'>Durée</th><th>Signature</th></tr></thead>" +
      "    <tbody>" + lignes + vides + "</tbody>" +
      '    <tfoot><tr class="total-row"><td colspan="5">Total des heures signées — ' + SM.escapeHtml(libelleMois(moisSel)) + "</td>" +
      '      <td style="text-align:right">' + fmtDuree(d.heuresTotal) + "</td><td></td></tr></tfoot>" +
      "  </table>" +
      '  <div class="bulletin-sign">' +
      '    <div>L’enseignant(e)<br>' + SM.escapeHtml(ens.prenom + " " + ens.nom) + '<br><span class="text-muted">Signature : ______________________</span></div>' +
      '    <div style="text-align:right">La direction<br><span class="text-muted">Cachet et signature : ______________________</span></div>' +
      "  </div>" +
      "</div></div>";
  }

  /* ---------- Événements ---------- */
  el("moisInput").addEventListener("change", function () { chargerMois(this.value); });
  el("btnPrint").addEventListener("click", function () {
    construireReleve();
    window.print();
  });
  el("btnSigner").addEventListener("click", function () {
    var fiche = ficheDuMois(moisSel);
    if (fiche && fiche.statut === "payee") {
      SM.toast("Ce mois a déjà été réglé : impossible d'ajouter une séance.", "warning");
      return;
    }
    SM.openModal("modalSeance");
  });
  el("btnSaveSeance").addEventListener("click", sauverSeance);
  el("fDebut").addEventListener("change", majDuree);
  el("fFin").addEventListener("change", majDuree);

  // Annulation d'une signature (délégation sur le tableau)
  document.getElementById("tableBody").addEventListener("click", function (e) {
    var b = e.target.closest("[data-del]");
    if (!b) return;
    var liste = etatMois ? etatMois.seances : [];
    for (var i = 0; i < liste.length; i++) {
      if (String(liste[i].id) === String(b.getAttribute("data-del"))) {
        seanceDel = liste[i];
        break;
      }
    }
    if (!seanceDel) return;
    el("delText").textContent = "La séance du " + SM.fmtDate(seanceDel.date) +
      " (" + seanceDel.classeNom + ", " + seanceDel.heureDebut + " – " + seanceDel.heureFin +
      ") sera retirée de votre cahier de présence. Cette action est irréversible.";
    SM.openModal("modalDel");
  });
  el("btnConfirmDel").addEventListener("click", confirmerAnnulation);

  /* ---------- Démarrage ---------- */
  chargerTout();
})();
