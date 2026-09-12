/* ============================================================
   SchoolManager — 💶 Rémunérations (direction)
   Barèmes (taux horaire par enseignant), récapitulatif mensuel
   du cahier de présence, génération des fiches de paie et
   validation des paiements.
   ============================================================ */

(function () {
  "use strict";

  var SM = window.SM;
  var API = window.API;

  // Accès décidé par le serveur (capacités de GET /api/v1/etat) : la page
  // n'est ouverte qu'aux profils qui possèdent l'opération d'écriture.
  if (!SM.peut("paie.ecrire")) {
    window.location.replace("dashboard.html");
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
  function moisCourantLocal() {
    var d = new Date();
    return d.getFullYear() + "-" + ("0" + (d.getMonth() + 1)).slice(-2);
  }
  function fmtDuree(h) {
    if (h === null || h === undefined || isNaN(h)) return "—";
    var total = Math.round(Number(h) * 60);
    var hh = Math.floor(total / 60);
    var mm = total % 60;
    return hh + " h " + ("0" + mm).slice(-2);
  }
  function erreur(e) {
    var msg = (e && e.detail) ? e.detail : (e && e.message) ? e.message : "Erreur inconnue.";
    SM.toast(String(msg), "error");
  }

  /* ---------- État ---------- */
  var moisSel = moisCourantLocal();
  var recaps = [];     // lignes du récapitulatif courant
  var baremes = [];    // enseignants + taux (barème)
  var pending = null;  // action en attente de confirmation

  function ficheDeLigne(ficheId) {
    for (var i = 0; i < recaps.length; i++) {
      if (recaps[i].ficheId !== null && String(recaps[i].ficheId) === String(ficheId)) return recaps[i];
    }
    return null;
  }

  /* ---------- Statistiques ---------- */
  function stats() {
    var enseignants = recaps.length;
    var heures = 0, aPayer = 0, dejaPaye = 0;
    recaps.forEach(function (l) {
      heures += Number(l.heures || 0);
      if (l.statutFiche === "payee") dejaPaye += Number(l.brut || 0);
      else aPayer += Number(l.brut || 0);
    });
    el("miniStats").innerHTML =
      '<div class="stat-card"><div class="stat-ico blue">👨‍🏫</div><div>' +
      '<div class="stat-value">' + enseignants + '</div><div class="stat-label">Enseignants concernés</div></div></div>' +
      '<div class="stat-card"><div class="stat-ico orange">🕐</div><div>' +
      '<div class="stat-value">' + fmtDuree(heures) + '</div><div class="stat-label">Heures signées</div></div></div>' +
      '<div class="stat-card"><div class="stat-ico purple">💶</div><div>' +
      '<div class="stat-value" style="font-size:21px">' + SM.formatFCFA(aPayer) + '</div><div class="stat-label">À payer (en attente)</div></div></div>' +
      '<div class="stat-card"><div class="stat-ico green">✅</div><div>' +
      '<div class="stat-value" style="font-size:21px">' + SM.formatFCFA(dejaPaye) + '</div><div class="stat-label">Déjà payé</div></div></div>';
  }

  /* ---------- Récapitulatif ---------- */
  function badgeFiche(l) {
    if (!l.statutFiche) return '<span class="text-muted">—</span>';
    return SM.badgeStatut(l.statutFiche === "payee" ? "Payée" : "En attente");
  }

  function actionsLigne(l) {
    var fid = l.ficheId;
    if (fid === null || fid === undefined) {
      return l.heures > 0
        ? '<span class="text-muted text-sm">À inclure lors de la génération</span>'
        : '<span class="text-muted text-sm">—</span>';
    }
    if (l.statutFiche === "payee") {
      return '<button class="btn btn-outline btn-sm" data-act="remettre" data-fid="' + fid + '">↩️ Remettre en attente</button>';
    }
    // en_attente
    return '<div class="row-actions" style="justify-content:center;gap:6px">' +
      '<button class="btn btn-success btn-sm" data-act="payer" data-fid="' + fid + '">✅ Marquer payée</button>' +
      '<button class="btn btn-danger-soft btn-sm" data-act="supprimer" data-fid="' + fid + '">🗑️ Supprimer</button>' +
      "</div>";
  }

  function renderRecap() {
    var body = el("recapBody");
    el("recapMoisLabel").textContent = "— " + libelleMois(moisSel);
    stats();

    if (!recaps.length) {
      body.innerHTML =
        '<tr><td colspan="7"><div class="empty-state"><div class="e-ico">📋</div><h4>Aucune séance signée ce mois</h4>' +
        "<p>Une fois que les enseignants auront signé leur cahier de présence (Ma présence), le récapitulatif et la génération des fiches apparaîtront ici.</p></div></td></tr>";
      el("recapCount").textContent = "0 enseignant concerné";
      return;
    }

    body.innerHTML = recaps.map(function (l) {
      var nomC = l.prenom + " " + l.nom;
      var taux;
      if (l.tauxHoraire > 0) {
        taux = SM.formatFCFA(l.tauxHoraire).replace(" FCFA", "") + " FCFA/h";
      } else {
        taux = '<span class="badge badge-warning">Taux non défini</span>';
      }
      var brut = l.brut > 0
        ? '<span class="fw-600" style="color:var(--success-text)">' + SM.formatFCFA(l.brut) + "</span>"
        : '<span class="text-muted">' + SM.formatFCFA(0) + "</span>";
      return (
        "<tr>" +
        '  <td><div class="cell-user">' + SM.avatarHTML(nomC, "sm") +
        '    <div><div class="names">' + SM.escapeHtml(l.nom) + " " + SM.escapeHtml(l.prenom) +
        '      </div><div class="sub">' + SM.escapeHtml(l.matiereNom) + "</div></div></div></td>" +
        "  <td>" + taux + "</td>" +
        '  <td><span class="fw-600">' + l.nbSeances + "</span></td>" +
        "  <td>" + fmtDuree(l.heures) + "</td>" +
        "  <td>" + brut + "</td>" +
        "  <td>" + badgeFiche(l) + "</td>" +
        '  <td><div style="display:flex;justify-content:center;gap:6px;flex-wrap:wrap">' + actionsLigne(l) + "</div></td>" +
        "</tr>"
      );
    }).join("");
    el("recapCount").textContent = recaps.length + " enseignant" + (recaps.length > 1 ? "s" : "") + " concerné" + (recaps.length > 1 ? "s" : "");
  }

  /* ---------- Barèmes ---------- */
  function renderBaremes() {
    var body = el("tauxBody");
    if (!baremes.length) {
      body.innerHTML =
        '<tr><td colspan="6"><div class="empty-state"><div class="e-ico">👨‍🏫</div><h4>Aucun enseignant enregistré</h4>' +
        "<p>Ajoutez d'abord des enseignants pour pouvoir fixer leurs taux horaires.</p></div></td></tr>";
      return;
    }
    body.innerHTML = baremes.map(function (t) {
      var nomC = t.nom + " " + t.prenom;
      return (
        "<tr>" +
        '  <td><div class="cell-user">' + SM.avatarHTML(t.prenom + " " + t.nom, "sm") +
        '    <div><div class="names">' + SM.escapeHtml(t.nom) + " " + SM.escapeHtml(t.prenom) +
        '      </div><div class="sub">' + SM.escapeHtml(t.id) + "</div></div></div></td>" +
        "  <td>" + SM.escapeHtml(t.matiereNom) + "</td>" +
        '  <td>' + SM.badgeStatut(t.statut) + "</td>" +
        '  <td><span class="chip-plain">' + t.nbClasses + " classe" + (t.nbClasses > 1 ? "s" : "") + "</span></td>" +
        '  <td><div style="display:flex;align-items:center;gap:8px">' +
        '    <input type="number" class="input" min="0" step="100" data-tid="' + SM.escapeHtml(t.id) + '" value="' + t.tauxHoraire + '" style="width:130px">' +
        '    <span class="text-muted" style="font-size:12.5px">FCFA / h</span></div></td>' +
        '  <td style="text-align:center"><button class="btn btn-outline btn-sm" data-savetaux="' + SM.escapeHtml(t.id) + '">💾 Enregistrer</button></td>' +
        "</tr>"
      );
    }).join("");
  }

  /* ---------- Chargements ---------- */
  function chargerRecap() {
    el("moisInput").value = moisSel;
    return API.paieRecap(moisSel)
      .then(function (d) {
        recaps = d.lignes || [];
        renderRecap();
      })
      .catch(erreur);
  }

  function chargerBaremes() {
    return API.paieEnseignants()
      .then(function (d) {
        baremes = d.enseignants || [];
        renderBaremes();
      })
      .catch(erreur);
  }

  function chargerTout() {
    el("moisInput").value = moisSel;
    chargerRecap();
    chargerBaremes();
  }

  /* ---------- Confirmation d'action ---------- */
  function ouvrirConfirmation(cfg) {
    pending = cfg;
    el("actionIco").textContent = cfg.ico || "⚠️";
    el("actionTitle").textContent = cfg.title || "Confirmer ?";
    el("actionText").innerHTML = cfg.text || "";
    el("btnConfirmAction").textContent = cfg.label || "Confirmer";
    SM.openModal("modalAction");
  }

  function messageResultat(html, type) {
    var zone = el("msgGen");
    zone.style.display = "";
    zone.innerHTML = '<div class="alert alert-' + (type || "success") + '"><div>' + html + "</div></div>";
  }
  function masquerMessage() {
    el("msgGen").style.display = "none";
    el("msgGen").innerHTML = "";
  }

  function executerAction() {
    if (!pending) return;
    var cfg = pending;
    pending = null;
    SM.closeModal("modalAction");

    if (cfg.type === "generer") {
      API.genererFiches(moisSel).then(function (r) {
        var parts = [];
        if (r.creees > 0) parts.push(r.creees + " fiche(s) créée(s)");
        if (r.maj > 0) parts.push(r.maj + " mise(s) à jour");
        if (r.payeesIgnorees > 0) parts.push(r.payeesIgnorees + " fiche(s) payée(s) ignorée(s)");
        var html = "✅ " + SM.escapeHtml("Fiches du mois de " + libelleMois(moisSel) + " générées : " + (parts.join(", ") || "aucune séance à traiter."));
        if (r.sansTaux && r.sansTaux.length) {
          html += '<br><br><strong>⚠️ Enseignants sans taux horaire (fiche à 0 FCFA) :</strong> ' +
            SM.escapeHtml(r.sansTaux.join(", ")) + " — fixez leur taux dans le barème puis régénérez.";
        }
        messageResultat(html, r.sansTaux && r.sansTaux.length ? "warning" : "success");
        return chargerRecap();
      }).catch(erreur);
      return;
    }

    var fid = cfg.ficheId;
    if (cfg.type === "payer" || cfg.type === "remettre") {
      var statut = cfg.type === "payer" ? "payee" : "en_attente";
      API.majStatutFiche(fid, { statut: statut })
        .then(function () {
          SM.toast(cfg.type === "payer" ? "Fiche marquée payée ✅" : "Fiche remise en attente", "success");
          masquerMessage();
          return chargerRecap();
        })
        .catch(erreur);
      return;
    }

    if (cfg.type === "supprimer") {
      API.supprimerFiche(fid)
        .then(function () {
          SM.toast("Fiche supprimée. Vous pouvez corriger les séances puis régénérer.", "success");
          masquerMessage();
          return chargerRecap();
        })
        .catch(erreur);
    }
  }

  /* ---------- Événements ---------- */
  el("moisInput").addEventListener("change", function () {
    moisSel = this.value || moisSel;
    masquerMessage();
    chargerRecap();
  });

  el("btnGenerer").addEventListener("click", function () {
    ouvrirConfirmation({
      type: "generer",
      ico: "⚙️",
      title: "Générer les fiches de paie ?",
      text: "Les fiches du mois de <strong>" + SM.escapeHtml(libelleMois(moisSel)) + "</strong> seront créées (ou mises à jour) à partir du cahier de présence signé. Les fiches déjà payées seront ignorées.",
      label: "Générer les fiches"
    });
  });

  el("btnConfirmAction").addEventListener("click", executerAction);

  // Actions sur les lignes du récapitulatif (payer / remettre / supprimer)
  el("recapBody").addEventListener("click", function (e) {
    var b = e.target.closest("[data-act]");
    if (!b) return;
    var act = b.getAttribute("data-act");
    var ligne = ficheDeLigne(b.getAttribute("data-fid"));
    if (!ligne) return;
    var nomC = ligne.prenom + " " + ligne.nom;
    var mois = libelleMois(moisSel);

    if (act === "payer") {
      ouvrirConfirmation({
        type: "payer",
        ico: "✅",
        title: "Marquer la fiche payée ?",
        text: "La fiche de <strong>" + SM.escapeHtml(nomC) + "</strong> (" + SM.escapeHtml(mois) + ") d'un montant de <strong>" + SM.formatFCFA(ligne.brut) + "</strong> sera marquée <strong>Payée</strong>. L'enseignant ne pourra plus modifier ce mois.",
        label: "Marquer payée",
        ficheId: ligne.ficheId
      });
      return;
    }
    if (act === "remettre") {
      ouvrirConfirmation({
        type: "remettre",
        ico: "↩️",
        title: "Contre-passer la fiche ?",
        text: "La fiche payée de <strong>" + SM.escapeHtml(nomC) + "</strong> (" + SM.escapeHtml(mois) + ") repasse en <strong>en attente</strong>. Les séances du mois restent gelées tant que la fiche existe : supprimez-la ensuite si une correction est nécessaire.",
        label: "Remettre en attente",
        ficheId: ligne.ficheId
      });
      return;
    }
    if (act === "supprimer") {
      ouvrirConfirmation({
        type: "supprimer",
        ico: "🗑️",
        title: "Supprimer cette fiche ?",
        text: "La fiche en attente de <strong>" + SM.escapeHtml(nomC) + "</strong> (" + SM.escapeHtml(mois) + ") sera supprimée. Vous pourrez corriger les séances du mois, puis régénérer la fiche.",
        label: "Supprimer la fiche",
        ficheId: ligne.ficheId
      });
    }
  });

  // Enregistrement d'un taux (délégation sur le tableau des barèmes)
  el("tauxBody").addEventListener("click", function (e) {
    var b = e.target.closest("[data-savetaux]");
    if (!b) return;
    var tid = b.getAttribute("data-savetaux");
    var input = el("tauxBody").querySelector('input[data-tid="' + tid + '"]');
    var valeur = input ? parseInt(input.value, 10) : NaN;
    if (isNaN(valeur) || valeur < 0) {
      SM.toast("Saisissez un taux horaire valide (nombre ≥ 0).", "error");
      return;
    }
    API.majTauxEnseignant(tid, { taux_horaire: valeur })
      .then(function () {
        SM.toast("Taux horaire enregistré : " + SM.formatFCFA(valeur), "success");
        chargerBaremes();
        chargerRecap();
      })
      .catch(erreur);
  });

  /* ---------- Démarrage ---------- */
  chargerTout();
})();
