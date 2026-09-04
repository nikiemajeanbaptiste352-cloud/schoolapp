/* ============================================================
   SchoolManager — Saisie des notes
   ============================================================ */

(function () {
  "use strict";

  var SM = window.SM;
  var SD = window.SD;

  function el(id) { return document.getElementById(id); }

  var params = new URLSearchParams(window.location.search);

  /* ---------- Remplissage des sélecteurs ---------- */
  var selClasse = el("selClasse");
  var selMatiere = el("selMatiere");
  var selEval = el("selEval");

  SD.classes.forEach(function (c) {
    var o = document.createElement("option");
    o.value = c.id;
    o.textContent = c.nom + " (" + c.cycle + ")";
    selClasse.appendChild(o);
  });
  if (params.get("classe")) selClasse.value = params.get("classe");

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

    el("titreSaisie").textContent = "Saisie des notes — " + (matiere ? matiere.nom : "") + " · " + (classe ? classe.nom : "");

    var tbody = el("tableBody");
    if (!liste.length) {
      tbody.innerHTML = '<tr><td colspan="5"><div class="empty-state"><div class="e-ico">🪑</div><h4>Aucun élève dans cette classe</h4></div></td></tr>';
      el("countLabel").textContent = "0 élève";
      return;
    }
    tbody.innerHTML = liste.map(function (e) {
      var note = noteEnregistree(e.id);
      var app = note ? SD.appreciation(note.note).mention : "";
      return (
        "<tr>" +
        '  <td class="text-center" id="rang-' + e.id + '"><span class="text-muted">…</span></td>' +
        '  <td><div class="cell-user">' + SM.avatarHTML(e.nom + " " + e.prenom, "sm") +
        '    <div><div class="names">' + SM.escapeHtml(e.nom) + " " + SM.escapeHtml(e.prenom) +
        '      </div><div class="sub">' + SM.escapeHtml(e.id) + (e.statut === "Inactif" ? ' · <span class="badge badge-warning">Inactif</span>' : "") + "</div></div></div></td>" +
        '  <td><span class="chip-plain">' + SM.escapeHtml(SD.getClasse(e.classe) ? SD.getClasse(e.classe).nom : e.classe) + "</span></td>" +
        '  <td style="text-align:center"><input type="number" class="input note-input" id="note-' + e.id + '" min="0" max="20" step="0.5" value="' + (note ? note.note : "") + '" placeholder="—"></td>' +
        '  <td id="app-' + e.id + '" class="text-sm">' + (note ? SM.escapeHtml(app) : '<span class="text-muted">—</span>') + "</td>" +
        "</tr>"
      );
    }).join("");
    el("countLabel").textContent = liste.length + " élève" + (liste.length > 1 ? "s" : "") + " dans la classe";
    majStats();
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
  el("btnSave").addEventListener("click", function () {
    var eleves = SD.elevesDeClasse(classeId());
    var nb = 0;
    eleves.forEach(function (e) {
      var val = saisiePour(e.id);
      var existant = noteEnregistree(e.id);
      if (val === null) {
        if (existant) {
          var i = SD.notes.indexOf(existant);
          if (i !== -1) SD.notes.splice(i, 1);
        }
        return;
      }
      var noteArrondie = Math.round(val * 2) / 2;
      if (existant) {
        existant.note = noteArrondie;
      } else {
        SD.notes.push({
          id: "N" + Date.now() + "-" + e.id,
          eleveId: e.id,
          classeId: classeId(),
          matiereId: matiereId(),
          eval: evalCourante(),
          note: noteArrondie
        });
      }
      nb++;
    });
    SM.toast(nb + " note" + (nb > 1 ? "s" : "") + " enregistrée" + (nb > 1 ? "s" : "") + " ✅", "success");
    majStats();
  });

  /* ---------- Changement de sélection ---------- */
  selClasse.addEventListener("change", function () { remplirMatieres(); charger(); });
  selMatiere.addEventListener("change", charger);
  selEval.addEventListener("change", charger);

  // Délégation unique : mise à jour en direct à la saisie
  el("tableBody").addEventListener("input", onSaisie);

  charger();
})();
