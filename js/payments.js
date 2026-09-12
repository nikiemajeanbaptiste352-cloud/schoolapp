/* ============================================================
   SchoolManager — Paiements
   ============================================================ */

(function () {
  "use strict";

  var SM = window.SM;
  var SD = window.SD;

  // Droit d'encaissement décidé par le serveur (capacités de GET /api/v1/etat) :
  // un élève ou un parent consulte ses paiements, il n'encaisse pas.
  var peutEncaisser = SM.peut("finance.ecrire");
  // Périmètre réduit (élève, parent) : les totaux parlent d'un dossier
  // personnel de scolarité, pas de la caisse de l'établissement.
  var estFamille = SM.porteeEleves() !== "tous";
  var role = SM.roleCourant();

  function el(id) { return document.getElementById(id); }

  /* ---------- Remplissage sélecteur d'élèves ---------- */
  var selEleve = el("fEleve");
  SD.eleves.slice().sort(function (a, b) {
    return (a.nom + a.prenom).localeCompare(b.nom + b.prenom, "fr");
  }).forEach(function (e) {
    var o = document.createElement("option");
    o.value = e.id;
    o.textContent = e.nom + " " + e.prenom + " — " + (SD.getClasse(e.classe) ? SD.getClasse(e.classe).nom : e.classe);
    selEleve.appendChild(o);
  });

  function dossierDe(eleveId) {
    var pai = SD.paiements.find(function (p) { return p.eleveId === eleveId; });
    if (pai) return pai;
    var elv = SD.getEleve(eleveId);
    var cls = SD.getClasse(elv.classe);
    var total = cls && cls.cycle === "Lycée" ? 200000 : 150000;
    pai = { eleveId: eleveId, motif: "Frais de scolarité " + SD.ecole.annee, total: total, paiements: [] };
    SD.paiements.push(pai);
    return pai;
  }

  /* ---------- Totaux ---------- */
  function totaux() {
    var attendu = 0, encaisse = 0;
    SD.paiements.forEach(function (p) {
      attendu += p.total;
      encaisse += SD.montantPaye(p);
    });
    var reste = attendu - encaisse;
    var taux = attendu ? Math.round((encaisse / attendu) * 100) : 0;
    var libelles = estFamille
      ? {
        attendu: role === "Parent" ? "Frais de scolarité" : "Mes frais de scolarité",
        encaisse: "Déjà versé",
        reste: role === "Parent" ? "Solde à payer" : "Mon solde à payer",
        taux: "Progression"
      }
      : { attendu: "Total attendu", encaisse: "Total encaissé", reste: "Reste à recouvrer", taux: "Taux de recouvrement" };
    el("summaryCards").innerHTML =
      '<div class="stat-card"><div class="stat-ico blue">📋</div><div><div class="stat-value">' + SM.formatFCFA(attendu) + '</div><div class="stat-label">' + libelles.attendu + '</div></div></div>' +
      '<div class="stat-card"><div class="stat-ico green">💵</div><div><div class="stat-value">' + SM.formatFCFA(encaisse) + '</div><div class="stat-label">' + libelles.encaisse + '</div></div></div>' +
      '<div class="stat-card"><div class="stat-ico red">⏳</div><div><div class="stat-value">' + SM.formatFCFA(reste) + '</div><div class="stat-label">' + libelles.reste + '</div></div></div>' +
      '<div class="stat-card"><div class="stat-ico orange">📈</div><div><div class="stat-value">' + taux + '%</div><div class="stat-label">' + libelles.taux + '</div></div></div>';
  }

  /* ---------- Rendu tableau ---------- */
  function render(liste) {
    var tbody = el("tableBody");
    // Colonnes retirées de l'écran : « Élève » quand un seul dossier est
    // visible, « Action » quand on n'a pas le droit d'encaisser.
    var masquerEleve = estFamille;
    var masquerAction = !peutEncaisser;
    var nbCols = 9 - (masquerEleve ? 1 : 0) - (masquerAction ? 1 : 0);
    if (!liste.length) {
      tbody.innerHTML = '<tr><td colspan="' + nbCols + '"><div class="empty-state"><div class="e-ico">💰</div><h4>Aucun dossier trouvé</h4></div></td></tr>';
      el("countLabel").textContent = "0 dossier";
      return;
    }
    tbody.innerHTML = liste.map(function (pai) {
      var e = SD.getEleve(pai.eleveId);
      if (!e) return "";
      var nomC = e.nom + " " + e.prenom;
      var paye = SD.montantPaye(pai);
      var reste = Math.max(0, pai.total - paye);
      var pct = Math.min(100, Math.round((paye / pai.total) * 100));
      var statut = SD.statutPaiement(pai);
      var barCls = statut === "Payé" ? "green" : statut === "Impayé" ? "red" : "orange";
      var dernier = SD.dernierPaiement(pai);
      return (
        "<tr>" +
        '  <td><div class="cell-user">' + SM.avatarHTML(nomC, "sm") +
        '    <div><div class="names">' + SM.escapeHtml(e.nom) + " " + SM.escapeHtml(e.prenom) +
        '      </div><div class="sub">' + SM.escapeHtml(e.id) + " · " + SM.escapeHtml(SD.getClasse(e.classe) ? SD.getClasse(e.classe).nom : e.classe) + "</div></div></div></td>" +
        "  <td><span class='text-sm fw-600'>" + SM.escapeHtml(pai.motif) + "</span></td>" +
        '  <td style="text-align:right" class="fw-600">' + SM.formatFCFA(pai.total) + "</td>" +
        '  <td style="text-align:right" class="text-success fw-600">' + SM.formatFCFA(paye) + "</td>" +
        '  <td style="text-align:right" class="fw-600' + (reste > 0 ? " text-danger" : "") + '">' + SM.formatFCFA(reste) + "</td>" +
        '  <td><div class="flex" style="gap:8px;align-items:center"><b style="font-size:12.5px;min-width:34px">' + pct + "%</b>" +
        '    <div class="progress" style="flex:1;height:8px"><div class="progress-bar ' + barCls + '" style="width:' + pct + '%"></div></div></div></td>' +
        "  <td>" + SM.badgeStatut(statut) + "</td>" +
        '  <td class="text-sm">' + (dernier
          ? SM.fmtDate(dernier.date) + " · " + SM.formatFCFA(dernier.montant)
          : '<span class="text-muted">—</span>') + "</td>" +
        '  <td style="text-align:center">' + (peutEncaisser
          ? '<button class="btn-icon primary-h" title="Encaisser" data-pay="' + e.id + '">💵</button>'
          : '<span class="text-muted">—</span>') + "</td>" +
        "</tr>"
      );
    }).join("");
    el("countLabel").textContent = liste.length + " dossier" + (liste.length > 1 ? "s" : "") + " de paiement";

    var ths = document.querySelectorAll("table.data thead th");
    if (masquerEleve && ths.length > 0) ths[0].style.display = "none";
    if (masquerAction && ths.length > 8) ths[8].style.display = "none";
    var tds = tbody.querySelectorAll("tr > td");
    for (var i = 0; i < tds.length; i++) {
      var pos = i % 9;
      if (masquerEleve && pos === 0) tds[i].style.display = "none";
      if (masquerAction && pos === 8) tds[i].style.display = "none";
    }
  }

  function actualiser() {
    totaux();
    var q = el("searchInput").value.toLowerCase().trim();
    if (!q) { render(SD.paiements); return; }
    var filtre = SD.paiements.filter(function (pai) {
      var e = SD.getEleve(pai.eleveId);
      if (!e) return false;
      return (e.nom + " " + e.prenom + " " + e.id).toLowerCase().indexOf(q) !== -1;
    });
    render(filtre);
  }

  totaux();
  render(SD.paiements);

  /* ---------- Recherche ---------- */
  el("searchInput").addEventListener("input", actualiser);

  /* ---------- Modale Encaisser ---------- */
  function ouvrirPay(eleveId) {
    var pai = dossierDe(eleveId);
    el("fEleve").value = eleveId;
    el("fMontant").value = "";
    el("fMode").value = "Espèces";
    el("fDate").value = new Date().toISOString().slice(0, 10);
    clearErreurs();
    var reste = Math.max(0, pai.total - SD.montantPaye(pai));
    el("payInfo").innerHTML = "💡 " + SM.escapeHtml(SD.getEleve(eleveId).nom + " " + SD.getEleve(eleveId).prenom) +
      " — reste <b>" + SM.formatFCFA(reste) + "</b> à payer sur " + SM.formatFCFA(pai.total) + ".";
    SM.openModal("modalPay");
  }

  // Ouverture via le bouton général « Encaisser »
  document.addEventListener("click", function (e) {
    var btn = e.target.closest('[data-open="modalPay"]');
    if (btn) {
      if (!peutEncaisser) { SM.toast("Consultation seule : vous n'avez pas le droit d'encaisser.", "warning"); return; }
      el("fEleve").value = SD.eleves.length ? SD.eleves[0].id : "";
      ouvrirPay(el("fEleve").value);
    }
  });

  function clearErreurs() {
    document.querySelectorAll(".field-error.show").forEach(function (x) { x.classList.remove("show"); });
    document.querySelectorAll(".input.invalid, .select.invalid").forEach(function (x) { x.classList.remove("invalid"); });
  }

  el("tableBody").addEventListener("click", function (e) {
    var btn = e.target.closest("[data-pay]");
    if (btn) {
      if (!peutEncaisser) { SM.toast("Consultation seule : vous n'avez pas le droit d'encaisser.", "warning"); return; }
      ouvrirPay(btn.getAttribute("data-pay"));
    }
  });

  /* ---------- Enregistrement d'un versement ---------- */
  el("btnSavePay").addEventListener("click", function () {
    // Encaissement réservé aux profils disposant de « finance.ecrire »
    // (décision du serveur, voir perimetre.py).
    if (!peutEncaisser) {
      SM.toast("Consultation seule : vous n'avez pas le droit d'encaisser.", "warning");
      return;
    }
    var eleveId = el("fEleve").value;
    var montant = parseInt(el("fMontant").value, 10);
    var date = el("fDate").value;
    if (!eleveId) {
      el("errEleve").classList.add("show");
      el("fEleve").classList.add("invalid");
      return;
    }
    if (!montant || montant <= 0) {
      el("errMontant").classList.add("show");
      el("fMontant").classList.add("invalid");
      SM.toast("Saisissez un montant valide.", "error");
      return;
    }
    var existaitDossier = SD.paiements.some(function (x) { return x.eleveId === eleveId; });
    var pai = dossierDe(eleveId);
    var corps = {
      montant: montant,
      date: date || new Date().toISOString().slice(0, 10),
      mode: el("fMode").value,
      // Utilisés par le serveur si aucun dossier n'existe encore
      motif: pai.motif,
      total: pai.total
    };
    var bouton = el("btnSavePay");
    bouton.disabled = true;
    bouton.textContent = "💾 Enregistrement…";
    API.versement(eleveId, corps).then(function (rep) {
      // Rejoue la mise à jour locale à partir de la réponse serveur
      var v = rep.versements && rep.versements.length ? rep.versements[rep.versements.length - 1] : null;
      var local = SD.paiements.find(function (x) { return x.eleveId === eleveId; });
      if (local) {
        local.total = rep.total;
        if (rep.motif) local.motif = rep.motif;
        if (v) local.paiements.push({ montant: v.montant, date: v.date, mode: v.mode || corps.mode });
      } else {
        SD.paiements.push({ eleveId: eleveId, motif: rep.motif, total: rep.total, paiements: v ? [v] : [] });
      }
      SM.closeModal("modalPay");
      SM.toast("Versement de " + SM.formatFCFA(montant) + " enregistré ✅", "success");
      actualiser();
    }).catch(function (err) {
      // Dossier local créé pour rien → on le retire pour rester fidèle au serveur
      if (!existaitDossier) {
        var i = SD.paiements.findIndex(function (x) { return x.eleveId === eleveId; });
        if (i !== -1) SD.paiements.splice(i, 1);
      }
      SM.toast("Encaissement impossible : " + (err && err.detail ? err.detail : "erreur réseau."), "error");
    }).then(function () {
      bouton.disabled = false;
      bouton.textContent = "💾 Enregistrer le versement";
    });
  });
})();
