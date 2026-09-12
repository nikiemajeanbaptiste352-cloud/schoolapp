/* ============================================================
   SchoolManager — Saisie des notes
   ============================================================ */

(function () {
  "use strict";

  var SM = window.SM;
  var SD = window.SD;

  function el(id) { return document.getElementById(id); }

  /* ---------- Rôle courant ----------
     Décisions issues du serveur (jamais de sessionStorage) :
       - notes.ecrire  → Administrateur, Professeur : saisie complète
       - portee        → élève/parent = un seul dossier : page de consultation */
  var role = SM.roleCourant();
  var estFamille = SM.porteeEleves() !== "tous";
  // Saisie réservée aux profils disposant de l'opération « notes.ecrire »
  // (Administrateur, Professeur) : décision du serveur, répercutée ici.
  var peutSaisirNotes = SM.peut("notes.ecrire");
  var lectureSeule = !peutSaisirNotes;

  var params = new URLSearchParams(window.location.search);

  /* ---------- Remplissage des sélecteurs ---------- */
  var selClasse = el("selClasse");
  var selMatiere = el("selMatiere");
  var selEval = el("selEval");

  // Structure de l'établissement : servie à tous, mais on ne propose au
  // périmètre réduit que la classe où se trouve l'élève visible — sinon le
  // sélecteur ouvrirait sur une classe vide (liste d'élèves filtrée).
  var classesListe = estFamille
    ? SD.classes.filter(function (c) {
      return SD.eleves.some(function (e) { return e.classe === c.id; });
    })
    : SD.classes;

  classesListe.forEach(function (c) {
    var o = document.createElement("option");
    o.value = c.id;
    o.textContent = c.nom + " (" + c.cycle + ")";
    selClasse.appendChild(o);
  });
  if (params.get("classe")) selClasse.value = params.get("classe");
  if (!selClasse.value && selClasse.options.length) selClasse.value = selClasse.options[0].value;

  SD.EVALS.forEach(function (ev) {
    var o = document.createElement("option");
    o.value = ev;
    o.textContent = ev;
    selEval.appendChild(o);
  });
  if (params.get("eval")) selEval.value = params.get("eval");

  function remplirMatieres() {
    var classeId = selClasse.value;
    var prec = selMatiere.value;
    selMatiere.innerHTML = "";
    SD.matieresDeClasse(classeId).forEach(function (m) {
      var o = document.createElement("option");
      o.value = m.id;
      o.textContent = m.icone + " " + m.nom + " (coef. " + m.coef + ")";
      selMatiere.appendChild(o);
    });
    if (prec && Array.prototype.some.call(selMatiere.options, function (o) { return o.value === prec; })) {
      selMatiere.value = prec;
    } else if (params.get("matiere") && Array.prototype.some.call(selMatiere.options, function (o) { return o.value === params.get("matiere"); })) {
      selMatiere.value = params.get("matiere");
    }
  }
  remplirMatieres();

  /* ---------- Habillage selon le rôle ---------- */
  // Périmètre réduit : une seule classe visible → le sélecteur « Classe »
  // n'apporte rien, et la synthèse personnelle remplace les statistiques
  // de classe (qui n'auraient aucun sens sur un effectif d'une personne).
  var titrePerso = el("titrePerso");
  if (estFamille) {
    if (selClasse.parentNode) selClasse.parentNode.style.display = "none";
    if (el("carteStatsEval")) el("carteStatsEval").style.display = "none";
    if (el("carteClassement")) el("carteClassement").style.display = "none";
    if (el("cartePerso")) el("cartePerso").style.display = "";
    if (titrePerso) {
      titrePerso.textContent = role === "Parent" ? "📊 Synthèse de votre enfant" : "📊 Ma synthèse";
    }
  }

  /* ---------- État courant ---------- */
  function classeId() { return selClasse.value; }
  function matiereId() { return selMatiere.value; }
  function evalCourante() { return selEval.value; }

  function noteEnregistree(eleveId) {
    return SD.notes.find(function (n) {
      return n.eleveId === eleveId && n.matiereId === matiereId() && n.eval === evalCourante();
    });
  }
  function saisiePour(eleveId) {
    var input = document.getElementById("note-" + eleveId);
    if (!input) return null;
    var v = input.value.trim();
    if (v === "") return null;
    var n = parseFloat(v);
    return isNaN(n) ? null : n;
  }

  /* ---------- Rendu du tableau ---------- */
  function charger() {
    var classe = SD.getClasse(classeId());
    var matiere = SD.getMatiere(matiereId());
    var liste = SD.elevesDeClasse(classeId());

    el("titreSaisie").textContent = (estFamille
      ? (role === "Parent" ? "Notes de l'élève" : "Mes notes")
      : "Saisie des notes") + " — " + (matiere ? matiere.nom : "") + (estFamille ? "" : " · " + (classe ? classe.nom : ""));

    var tbody = el("tableBody");
    if (!liste.length) {
      tbody.innerHTML = '<tr><td colspan="' + (estFamille ? 4 : 5) + '"><div class="empty-state"><div class="e-ico">🪑</div><h4>Aucun élève dans cette classe</h4></div></td></tr>';
      el("countLabel").textContent = "0 élève";
      return;
    }
    tbody.innerHTML = liste.map(function (e) {
      var note = noteEnregistree(e.id);
      var app = note ? SD.appreciation(note.note).mention : "";
      // Rang : pour un périmètre réduit, seul le serveur connaît le
      // classement réel (il voit toute la classe) → on utilise e.rang.
      var rang = estFamille
        ? (e.rang ? '<span class="rank-pill ' + (e.rang.rang === 1 ? "r1" : e.rang.rang === 2 ? "r2" : e.rang.rang === 3 ? "r3" : "") + '">' + e.rang.rang + "</span>" : '<span class="text-muted">—</span>')
        : '<span class="text-muted">…</span>';
      var cellNote = lectureSeule
        ? '  <td style="text-align:center">' + (note ? "<b>" + String(note.note).replace(".", ",") + "</b>" : '<span class="text-muted">—</span>') + "</td>"
        : '  <td style="text-align:center"><input type="number" class="input note-input" id="note-' + e.id + '" min="0" max="20" step="0.5" value="' + (note ? note.note : "") + '" placeholder="—"></td>';
      return (
        "<tr>" +
        '  <td class="text-center" id="rang-' + e.id + '">' + rang + "</td>" +
        '  <td><div class="cell-user">' + SM.avatarHTML(e.nom + " " + e.prenom, "sm") +
        '    <div><div class="names">' + SM.escapeHtml(e.nom) + " " + SM.escapeHtml(e.prenom) +
        '      </div><div class="sub">' + SM.escapeHtml(e.id) + (e.statut === "Inactif" ? ' · <span class="badge badge-warning">Inactif</span>' : "") + "</div></div></div></td>" +
        '  <td><span class="chip-plain">' + SM.escapeHtml(SD.getClasse(e.classe) ? SD.getClasse(e.classe).nom : e.classe) + "</span></td>" +
        cellNote +
        '  <td id="app-' + e.id + '" class="text-sm">' + (note ? SM.escapeHtml(app) : '<span class="text-muted">—</span>') + "</td>" +
        "</tr>"
      );
    }).join("");
    el("countLabel").textContent = estFamille
      ? (liste.length + " élève" + (liste.length > 1 ? "s" : ""))
      : (liste.length + " élève" + (liste.length > 1 ? "s" : "") + " dans la classe");
    // La colonne « Classe » est redondante quand une seule classe est visible :
    // on masque l'en-tête et la cellule ensemble pour garder l'alignement.
    if (estFamille) {
      var ths = document.querySelectorAll("table.data thead th");
      if (ths.length > 2) ths[2].style.display = "none";
      var tds = tbody.querySelectorAll("tr > td:nth-child(3)");
      for (var i = 0; i < tds.length; i++) tds[i].style.display = "none";
      majSynthPerso(liste[0]);
    }
    majStats();
  }

  /* Synthèse personnelle (moyenne générale + rang serveur) */
  function majSynthPerso(eleve) {
    if (!eleve) return;
    var moy = SD.moyennesEleve(eleve.id);
    var r = SD.rangEleve(eleve.id);
    if (el("persoMoyenne")) el("persoMoyenne").textContent = moy.generale.toFixed(2).replace(".", ",") + "/20";
    if (el("persoRang")) el("persoRang").textContent = r ? r.rang + "e / " + r.total : "—";
    if (el("persoMention")) el("persoMention").textContent = SD.appreciation(moy.generale).mention;
  }

  /* ---------- Mise à jour à la saisie ---------- */
  function onSaisie(e) {
    var input = e.target;
    if (!input.classList.contains("note-input")) return;
    var eleveId = input.id.replace("note-", "");
    var v = parseFloat(input.value);
    var cellApp = document.getElementById("app-" + eleveId);
    if (cellApp) {
      if (!isNaN(v)) {
        var mention = SD.appreciation(v).mention;
        cellApp.textContent = mention;
      } else {
        cellApp.innerHTML = '<span class="text-muted">—</span>';
      }
    }
    majStats();
  }

  /* ---------- Statistiques & classement ---------- */
  function majStats() {
    // Périmètre réduit : pas de statistiques de classe (l'effectif visible
    // vaut 1) et le rang affiché vient du serveur, pas de ce calcul local.
    if (estFamille) return;
    var eleves = SD.elevesDeClasse(classeId());
    var rows = [];
    eleves.forEach(function (e) {
      var note = saisiePour(e.id);
      rows.push({ e: e, note: note });
    });

    var notesValides = rows.filter(function (r) { return r.note !== null; }).map(function (r) { return r.note; });
    el("statCompteur").textContent = notesValides.length + " / " + eleves.length;

    if (notesValides.length) {
      var moy = notesValides.reduce(function (a, b) { return a + b; }, 0) / notesValides.length;
      var max = Math.max.apply(null, notesValides);
      var min = Math.min.apply(null, notesValides);
      el("statMoyenne").textContent = moy.toFixed(2).replace(".", ",") + "/20";
      el("statMax").textContent = max.toFixed(2).replace(".", ",") + "/20";
      el("statMin").textContent = min.toFixed(2).replace(".", ",") + "/20";
    } else {
      el("statMoyenne").textContent = "—";
      el("statMax").textContent = "—";
      el("statMin").textContent = "—";
    }

    // Classement : élèves notés d'abord, triés par note décroissante
    var classes_ = rows.slice().sort(function (a, b) {
      if (a.note === null && b.note === null) return 0;
      if (a.note === null) return 1;
      if (b.note === null) return -1;
      return b.note - a.note;
    });

    var html = classes_.map(function (r, i) {
      var pill = "";
      if (r.note !== null) {
        pill = '<span class="rank-pill ' + (i === 0 ? "r1" : i === 1 ? "r2" : i === 2 ? "r3" : "") + '">' + (i + 1) + "</span>";
      }
      return (
        '<div class="settings-row" style="padding:8px 0">' +
        '  <div class="flex" style="gap:10px;align-items:center">' + pill +
        '    <div><div class="fw-600" style="font-size:13.5px">' + SM.escapeHtml(r.e.nom + " " + r.e.prenom) + "</div>" +
        '      <div class="text-xs text-muted">' + SM.escapeHtml(r.e.id) + "</div></div></div>" +
        '  <b style="font-size:14px">' + (r.note !== null ? r.note.toFixed(2).replace(".", ",") : '<span class="text-muted">—</span>') + "</b>" +
        "</div>"
      );
    }).join("");
    el("listeRangs").innerHTML = html || '<p class="text-soft text-sm">Aucune note saisie.</p>';

    // Mise à jour de la colonne Rang du tableau
    classes_.forEach(function (r, i) {
      var cell = document.getElementById("rang-" + r.e.id);
      if (!cell) return;
      if (r.note === null) { cell.innerHTML = '<span class="text-muted">—</span>'; return; }
      var cls = i === 0 ? "r1" : i === 1 ? "r2" : i === 2 ? "r3" : "";
      cell.innerHTML = '<span class="rank-pill ' + cls + '">' + (i + 1) + "</span>";
    });
  }

  /* ---------- Enregistrement ---------- */
  if (lectureSeule) {
    var btnSaisie = el("btnSave");
    if (btnSaisie) btnSaisie.style.display = "none";
  }

  el("btnSave").addEventListener("click", function () {
    if (!peutSaisirNotes) {
      SM.toast("Consultation seule : vous n'avez pas le droit de saisir les notes.", "warning");
      return;
    }
    var eleves = SD.elevesDeClasse(classeId());
    var notes = [];
    var aSupprimer = [];
    eleves.forEach(function (e) {
      var val = saisiePour(e.id);
      var existant = noteEnregistree(e.id);
      if (val === null) {
        // Case vidée : une note existante doit être supprimée côté serveur
        if (existant) aSupprimer.push(existant);
        return;
      }
      var noteArrondie = Math.round(val * 2) / 2;
      notes.push({ eleveId: e.id, matiereId: matiereId(), eval: evalCourante(), note: noteArrondie });
    });

    if (!notes.length && !aSupprimer.length) {
      SM.toast("Aucune note à enregistrer.", "warning");
      majStats();
      return;
    }

    var bouton = el("btnSave");
    bouton.disabled = true;
    bouton.textContent = "Enregistrement…";

    var operations = [];
    // Suppressions (notes vidées)
    aSupprimer.forEach(function (n) {
      operations.push(API.supprimerNote(n.eleveId, n.matiereId, n.eval).then(function () {
        var i = SD.notes.indexOf(n);
        if (i !== -1) SD.notes.splice(i, 1);
      }));
    });
    // Enregistrements / mises à jour
    if (notes.length) {
      operations.push(API.enregistrerNotes({ notes: notes }).then(function () {
        notes.forEach(function (saisie) {
          var n = SD.notes.find(function (x) {
            return x.eleveId === saisie.eleveId && x.matiereId === saisie.matiereId && x.eval === saisie.eval;
          });
          if (n) {
            n.note = saisie.note;
          } else {
            SD.notes.push({
              id: "N" + Date.now() + "-" + saisie.eleveId,
              eleveId: saisie.eleveId,
              classeId: classeId(),
              matiereId: saisie.matiereId,
              eval: saisie.eval,
              note: saisie.note
            });
          }
        });
      }));
    }

    Promise.all(operations).then(function () {
      var retrait = aSupprimer.length;
      SM.toast(
        notes.length + " note" + (notes.length > 1 ? "s" : "") + " enregistrée" + (notes.length > 1 ? "s" : "") +
        (retrait ? " · " + retrait + " supprimée" + (retrait > 1 ? "s" : "") : "") + " ✅",
        "success"
      );
      majStats();
    }).catch(function (err) {
      SM.toast("Enregistrement impossible : " + (err && err.detail ? err.detail : "erreur réseau."), "error");
    }).then(function () {
      bouton.disabled = false;
      bouton.textContent = "💾 Enregistrer les notes";
    });
  });

  /* ---------- Changement de sélection ---------- */
  selClasse.addEventListener("change", function () { remplirMatieres(); charger(); });
  selMatiere.addEventListener("change", charger);
  selEval.addEventListener("change", charger);

  // Délégation unique : mise à jour en direct à la saisie
  el("tableBody").addEventListener("input", onSaisie);

  charger();
})();
